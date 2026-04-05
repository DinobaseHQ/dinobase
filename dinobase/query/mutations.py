"""Mutation engine — handles writes back to source systems via SQL.

Flow:
1. Agent writes SQL (UPDATE/INSERT/DELETE, single or multi-statement, cross-source)
2. Engine parses each statement, validates guardrails, generates a preview
3. Agent confirms the mutation batch
4. Engine executes locally then calls each source API per affected row
5. Everything is logged in _dinobase.mutations with per-row results

Guardrails:
- Only UPDATE, INSERT, and DELETE allowed (no DROP, ALTER, TRUNCATE)
- DELETE requires a WHERE clause (no bulk deletes)
- Preview by default — shows diff per row, doesn't execute
- Row limit — blocks mutations affecting too many rows
- Audit log — every mutation is recorded with per-row API results
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from typing import Any

from dinobase.db import DinobaseDB, META_SCHEMA


BLOCKED_STATEMENTS = {"DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"}
DEFAULT_MAX_AFFECTED_ROWS = 50
PENDING_TTL_MINUTES = 10


class MutationEngine:
    def __init__(self, db: DinobaseDB):
        self.db = db

    def _expire_stale(self) -> None:
        """Auto-expire pending mutations older than PENDING_TTL_MINUTES."""
        self.db.conn.execute(
            f"UPDATE {META_SCHEMA}.mutations SET status = 'expired' "
            f"WHERE status = 'pending' "
            f"AND created_at < current_timestamp - INTERVAL '{PENDING_TTL_MINUTES} minutes'"
        )

    def handle_sql(
        self, sql: str, max_affected_rows: int = DEFAULT_MAX_AFFECTED_ROWS
    ) -> dict[str, Any]:
        """Handle one or more SQL mutations. Splits multi-statement SQL and
        creates a single mutation batch with previews for all statements.

        Append --force to skip the confirmation step and execute immediately.
        """
        self._expire_stale()

        # Check for --force flag
        force = False
        stripped = sql.strip()
        if stripped.endswith("--force"):
            force = True
            sql = stripped[:-len("--force")].strip()

        statements = _split_statements(sql)
        if not statements:
            return {"error": "Empty SQL"}

        # Single statement — return flat preview
        if len(statements) == 1:
            result = self._handle_single(statements[0], max_affected_rows)
        else:
            # Multi-statement — return a batch preview
            result = self._handle_batch(statements, max_affected_rows)

        # Auto-confirm if --force was specified
        if force and "error" not in result:
            if "mutation_id" in result:
                return self.confirm(result["mutation_id"])
            elif "mutations" in result:
                mutation_ids = [m["mutation_id"] for m in result["mutations"]]
                return self.confirm_batch(mutation_ids)

        return result

    def _handle_single(
        self, sql: str, max_affected_rows: int
    ) -> dict[str, Any]:
        parsed = _parse_mutation_sql(sql)
        if "error" in parsed:
            return parsed

        source_info = self._get_source_info(parsed["schema"])
        if source_info is None:
            return {"error": f"Schema '{parsed['schema']}' is not a known source."}

        if parsed["operation"] == "UPDATE":
            return self._preview_update(sql, parsed, source_info, max_affected_rows)
        elif parsed["operation"] == "INSERT":
            return self._preview_insert(sql, parsed, source_info)
        elif parsed["operation"] == "DELETE":
            return self._preview_delete(sql, parsed, source_info, max_affected_rows)
        return {"error": f"Unsupported operation: {parsed['operation']}"}

    def _handle_batch(
        self, statements: list[str], max_affected_rows: int
    ) -> dict[str, Any]:
        """Handle multi-statement SQL as a single mutation batch."""
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"
        previews = []
        errors = []

        for stmt in statements:
            result = self._handle_single(stmt, max_affected_rows)
            if "error" in result:
                errors.append({"sql": stmt, "error": result["error"]})
            else:
                previews.append(result)

        if errors and not previews:
            return {"error": "All statements failed validation", "details": errors}

        # Group mutation IDs under a batch
        mutation_ids = [p["mutation_id"] for p in previews]

        # Track which sources are involved
        sources_involved = list({
            p["preview"]["source"] for p in previews
        })

        return {
            "batch_id": batch_id,
            "status": "pending_confirmation",
            "statements": len(statements),
            "valid": len(previews),
            "errors": errors if errors else None,
            "sources_involved": sources_involved,
            "mutations": previews,
            "confirm": f"Call confirm for each mutation_id, or confirm_batch with all IDs: {mutation_ids}",
        }

    def confirm(self, mutation_id: str) -> dict[str, Any]:
        """Confirm and execute a pending mutation."""
        self._expire_stale()
        res = self.db.conn.execute(
            f"SELECT * FROM {META_SCHEMA}.mutations WHERE mutation_id = ?",
            [mutation_id],
        )
        cols = [d[0] for d in res.description]
        rows = [dict(zip(cols, row)) for row in res.fetchall()]
        if not rows:
            return {"error": f"Mutation '{mutation_id}' not found"}

        mutation = rows[0]
        if mutation["status"] != "pending":
            return {"error": f"Mutation '{mutation_id}' is {mutation['status']}, not pending"}

        result = self._execute_mutation(mutation)

        status = "executed" if "error" not in result else "failed"
        self.db.conn.execute(
            f"UPDATE {META_SCHEMA}.mutations SET "
            f"status = ?, confirmed_at = current_timestamp, "
            f"executed_at = current_timestamp, result = ?, error_message = ? "
            f"WHERE mutation_id = ?",
            [status, json.dumps(result, default=str), result.get("error"), mutation_id],
        )
        return result

    def confirm_batch(self, mutation_ids: list[str]) -> dict[str, Any]:
        """Confirm and execute multiple mutations (for multi-statement SQL)."""
        results = []
        for mid in mutation_ids:
            results.append(self.confirm(mid))

        succeeded = sum(1 for r in results if r.get("status") == "executed")
        failed = sum(1 for r in results if "error" in r)

        return {
            "status": "batch_executed",
            "total": len(mutation_ids),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    def list_pending(self) -> list[dict[str, Any]]:
        return self.db.query(
            f"SELECT mutation_id, source_name, table_name, operation, sql_text, "
            f"preview, created_at FROM {META_SCHEMA}.mutations "
            f"WHERE status = 'pending' ORDER BY created_at"
        )

    def cancel(self, mutation_id: str) -> dict[str, Any]:
        res = self.db.conn.execute(
            f"SELECT status FROM {META_SCHEMA}.mutations WHERE mutation_id = ?",
            [mutation_id],
        )
        rows = [{"status": row[0]} for row in res.fetchall()]
        if not rows:
            return {"error": f"Mutation '{mutation_id}' not found"}
        if rows[0]["status"] != "pending":
            return {"error": f"Mutation '{mutation_id}' is {rows[0]['status']}, not pending"}

        self.db.conn.execute(
            f"UPDATE {META_SCHEMA}.mutations SET status = 'cancelled' "
            f"WHERE mutation_id = ? AND status = 'pending'",
            [mutation_id],
        )
        return {"status": "cancelled", "mutation_id": mutation_id}

    # --- Preview generation ---

    def _preview_update(
        self, sql: str, parsed: dict, source_info: dict, max_affected_rows: int
    ) -> dict[str, Any]:
        schema = parsed["schema"]
        table = parsed["table"]
        where_clause = parsed.get("where", "")
        set_clause = parsed.get("set_clause", "")

        if where_clause:
            err = _validate_where_clause(where_clause)
            if err:
                return {"error": f"Invalid WHERE clause: {err}"}

        count_sql = f'SELECT COUNT(*) as cnt FROM "{schema}"."{table}"'
        if where_clause:
            count_sql += f" WHERE {where_clause}"

        try:
            affected = self.db.query(count_sql)[0]["cnt"]
        except Exception as e:
            return {"error": f"Failed to count affected rows: {e}"}

        if affected == 0:
            return {"error": "No rows match the WHERE clause. Nothing to update."}

        if affected > max_affected_rows:
            return {
                "error": f"This UPDATE would affect {affected} rows (limit: {max_affected_rows}). "
                f"Add a more specific WHERE clause or increase max_affected_rows.",
                "rows_affected": affected,
            }

        # Fetch ALL affected rows (not just 10) — we need their IDs for per-row API calls
        select_sql = f'SELECT * FROM "{schema}"."{table}"'
        if where_clause:
            select_sql += f" WHERE {where_clause}"

        try:
            current_rows = self.db.query(select_sql)
        except Exception as e:
            return {"error": f"Failed to fetch affected rows: {e}"}

        changes = _parse_set_clause(set_clause)

        row_previews = []
        for row in current_rows:
            preview = {"id": row.get("id", "unknown")}
            for col, new_val in changes.items():
                old_val = row.get(col)
                if old_val is not None:
                    preview[col] = f"{old_val} → {new_val}"
                else:
                    preview[col] = f"NULL → {new_val}"
            row_previews.append(preview)

        mutation_id = f"mut_{uuid.uuid4().hex[:12]}"

        preview_data = {
            "operation": "UPDATE",
            "source": schema,
            "table": table,
            "rows_affected": affected,
            "changes": row_previews,
            "side_effects": [
                f"Will call API to update {affected} record(s) in {source_info['type']} "
                f"(one API call per row)"
            ],
        }

        self.db.conn.execute(
            f"INSERT INTO {META_SCHEMA}.mutations "
            f"(mutation_id, source_name, table_name, operation, sql_text, preview, status) "
            f"VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            [mutation_id, schema, table, "UPDATE", sql, json.dumps(preview_data, default=str)],
        )

        return {
            "mutation_id": mutation_id,
            "status": "pending_confirmation",
            "preview": preview_data,
            "confirm": f"Call confirm with mutation_id '{mutation_id}' to execute",
        }

    def _preview_insert(
        self, sql: str, parsed: dict, source_info: dict
    ) -> dict[str, Any]:
        schema = parsed["schema"]
        table = parsed["table"]
        columns = parsed.get("columns", [])
        values = parsed.get("values", [])

        mutation_id = f"mut_{uuid.uuid4().hex[:12]}"

        preview_data = {
            "operation": "INSERT",
            "source": schema,
            "table": table,
            "rows_to_insert": 1,
            "data": dict(zip(columns, values)) if columns and values else {"raw_sql": sql},
            "side_effects": [
                f"Will call API to create 1 record in {source_info['type']}"
            ],
        }

        self.db.conn.execute(
            f"INSERT INTO {META_SCHEMA}.mutations "
            f"(mutation_id, source_name, table_name, operation, sql_text, preview, status) "
            f"VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            [mutation_id, schema, table, "INSERT", sql, json.dumps(preview_data, default=str)],
        )

        return {
            "mutation_id": mutation_id,
            "status": "pending_confirmation",
            "preview": preview_data,
            "confirm": f"Call confirm with mutation_id '{mutation_id}' to execute",
        }

    def _preview_delete(
        self, sql: str, parsed: dict, source_info: dict, max_affected_rows: int
    ) -> dict[str, Any]:
        schema = parsed["schema"]
        table = parsed["table"]
        where_clause = parsed["where"]  # guaranteed non-empty by parser

        err = _validate_where_clause(where_clause)
        if err:
            return {"error": f"Invalid WHERE clause: {err}"}

        count_sql = f'SELECT COUNT(*) as cnt FROM "{schema}"."{table}" WHERE {where_clause}'
        try:
            affected = self.db.query(count_sql)[0]["cnt"]
        except Exception as e:
            return {"error": f"Failed to count affected rows: {e}"}

        if affected == 0:
            return {"error": "No rows match the WHERE clause. Nothing to delete."}

        if affected > max_affected_rows:
            return {
                "error": f"This DELETE would affect {affected} rows (limit: {max_affected_rows}). "
                f"Add a more specific WHERE clause or increase max_affected_rows.",
                "rows_affected": affected,
            }

        select_sql = f'SELECT * FROM "{schema}"."{table}" WHERE {where_clause}'
        try:
            doomed_rows = self.db.query(select_sql)
        except Exception as e:
            return {"error": f"Failed to fetch affected rows: {e}"}

        row_previews = []
        for row in doomed_rows:
            row_previews.append({k: str(v) if v is not None else "NULL" for k, v in row.items()})

        mutation_id = f"mut_{uuid.uuid4().hex[:12]}"

        preview_data = {
            "operation": "DELETE",
            "source": schema,
            "table": table,
            "rows_affected": affected,
            "rows_to_delete": row_previews,
            "side_effects": [
                f"Will call API to delete {affected} record(s) from {source_info['type']} "
                f"(one API call per row)"
            ],
        }

        self.db.conn.execute(
            f"INSERT INTO {META_SCHEMA}.mutations "
            f"(mutation_id, source_name, table_name, operation, sql_text, preview, status) "
            f"VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            [mutation_id, schema, table, "DELETE", sql, json.dumps(preview_data, default=str)],
        )

        return {
            "mutation_id": mutation_id,
            "status": "pending_confirmation",
            "preview": preview_data,
            "confirm": f"Call confirm with mutation_id '{mutation_id}' to execute",
        }

    # --- Execution ---

    def _execute_mutation(self, mutation: dict) -> dict[str, Any]:
        schema = mutation["source_name"]
        table = mutation["table_name"]
        operation = mutation["operation"]
        sql = mutation["sql_text"]

        source_info = self._get_source_info(schema)
        if source_info is None:
            return {"error": f"Source '{schema}' no longer configured"}

        # Write back to source API — per row for updates, single call for inserts
        api_results = self._write_back_to_source(schema, table, operation, mutation)

        # Update local data for read-after-write consistency.
        # We write to the staging table (_live_<table>) which the view merges
        # with the parquet data. This makes the change immediately queryable.
        local_result = self._update_local(schema, table, operation, mutation)

        print(
            f"[mutation] Executed {operation} on {schema}.{table} "
            f"(mutation_id: {mutation['mutation_id']})",
            file=sys.stderr,
        )

        result: dict[str, Any] = {
            "status": "executed",
            "mutation_id": mutation["mutation_id"],
            "operation": operation,
            "source": schema,
            "table": table,
        }

        if api_results is not None:
            result["api_write_back"] = api_results
        else:
            result["api_write_back"] = "skipped (no write config for this source)"

        if local_result:
            result["local_update"] = local_result

        return result

    def _update_local(
        self, schema: str, table: str, operation: str, mutation: dict
    ) -> dict[str, Any] | None:
        """Update the local staging table for read-after-write consistency.

        For views over parquet, we can't UPDATE the view directly. Instead we
        upsert rows into the staging table (_live_<table>) which the view
        merges with parquet data.
        """
        preview = mutation.get("preview")
        if isinstance(preview, str):
            preview = json.loads(preview)
        if not preview:
            return None

        staging_table = f"_live_{table}"

        # Check if staging table exists
        tables = self.db.get_tables(schema)
        if staging_table not in tables:
            # No staging table — try direct SQL (works for real tables)
            try:
                self.db.conn.execute(mutation["sql_text"])
                return {"method": "direct_sql"}
            except Exception:
                return {"method": "skipped", "reason": "no staging table"}

        if operation == "UPDATE":
            changes_list = preview.get("changes", [])
            set_fields = _parse_set_clause(preview.get("set_clause", ""))
            # If set_clause not in preview, extract from changes
            if not set_fields and changes_list:
                for change in changes_list:
                    for key, val in change.items():
                        if key == "id":
                            continue
                        if "→" in str(val):
                            set_fields[key] = str(val).split("→")[-1].strip()

            rows_upserted = 0
            for change in changes_list:
                record_id = str(change.get("id", ""))
                if not record_id or record_id == "unknown":
                    continue

                # Fetch the full current row from the view (parquet data)
                try:
                    result = self.db.conn.execute(
                        f'SELECT * FROM "{schema}"."{table}" WHERE CAST(id AS VARCHAR) = ? LIMIT 1',
                        [record_id],
                    )
                    cols = [d[0] for d in result.description]
                    rows = result.fetchall()
                    current = [dict(zip(cols, r)) for r in rows]
                except Exception:
                    current = []

                if current:
                    row = dict(current[0])
                    # Apply changes
                    for col, new_val in set_fields.items():
                        if col in row:
                            row[col] = new_val

                    # Delete existing staging row if any, then insert
                    self.db.conn.execute(
                        f'DELETE FROM "{schema}"."{staging_table}" WHERE CAST(id AS VARCHAR) = ?',
                        [record_id],
                    )
                    columns = list(row.keys())
                    placeholders = ", ".join(["?"] * len(columns))
                    col_names = ", ".join(f'"{c}"' for c in columns)
                    self.db.conn.execute(
                        f'INSERT INTO "{schema}"."{staging_table}" ({col_names}) VALUES ({placeholders})',
                        list(row.values()),
                    )
                    rows_upserted += 1

            return {"method": "staging_table", "rows_upserted": rows_upserted}

        elif operation == "INSERT":
            data = preview.get("data", {})
            if "raw_sql" in data:
                # Try direct SQL insert
                try:
                    self.db.conn.execute(
                        mutation["sql_text"].replace(
                            f'"{schema}"."{table}"', f'"{schema}"."{staging_table}"'
                        ).replace(
                            f'{schema}.{table}', f'"{schema}"."{staging_table}"'
                        )
                    )
                    return {"method": "staging_table", "rows_inserted": 1}
                except Exception:
                    return {"method": "skipped", "reason": "insert parse failed"}

            columns = list(data.keys())
            if columns:
                placeholders = ", ".join(["?"] * len(columns))
                col_names = ", ".join(f'"{c}"' for c in columns)
                self.db.conn.execute(
                    f'INSERT INTO "{schema}"."{staging_table}" ({col_names}) VALUES ({placeholders})',
                    list(data.values()),
                )
                return {"method": "staging_table", "rows_inserted": 1}

        elif operation == "DELETE":
            rows_to_delete = preview.get("rows_to_delete", [])
            if not rows_to_delete:
                return None

            deleted_ids = []
            for row in rows_to_delete:
                record_id = str(row.get("id", ""))
                if not record_id or record_id == "NULL":
                    continue
                self.db.conn.execute(
                    f'DELETE FROM "{schema}"."{staging_table}" WHERE CAST(id AS VARCHAR) = ?',
                    [record_id],
                )
                deleted_ids.append(record_id)

            # Execute the original DELETE against the table directly
            try:
                self.db.conn.execute(mutation["sql_text"])
                return {"method": "direct_sql", "rows_deleted": len(deleted_ids)}
            except Exception:
                # View-based delete may fail; staging cleanup + API call is authoritative
                return {"method": "staging_cleanup", "rows_cleaned": len(deleted_ids)}

        return None

    def _write_back_to_source(
        self, schema: str, table: str, operation: str, mutation: dict
    ) -> dict[str, Any] | None:
        from dinobase.sync.write_client import WriteClient

        source_info = self._get_source_info(schema)
        if source_info is None:
            return None

        credentials = source_info.get("credentials", {})
        client = WriteClient(schema, credentials)

        if not client.has_config or not client.write_endpoints:
            return None

        endpoint_name = self._match_write_endpoint(client, table, operation)
        if endpoint_name is None:
            return {
                "status": "no_matching_endpoint",
                "available": [ep["name"] for ep in client.write_endpoints],
            }

        preview = mutation.get("preview")
        if isinstance(preview, str):
            preview = json.loads(preview)

        endpoint = client.config and get_endpoint_from_config(client.config, endpoint_name)
        is_bulk = endpoint.get("bulk", False) if endpoint else False
        max_batch = endpoint.get("max_batch_size", 100) if endpoint else 100

        if operation == "UPDATE" and preview:
            changes = preview.get("changes", [])
            if not changes:
                return None

            # Per-row API calls (or batch if endpoint supports it)
            row_results = []
            batch = []

            for change in changes:
                record_id = str(change.get("id", ""))
                data = {}
                for key, val in change.items():
                    if key == "id":
                        continue
                    if "→" in str(val):
                        data[key] = str(val).split("→")[-1].strip()
                    else:
                        data[key] = val

                if is_bulk:
                    batch.append({"id": record_id, **data})
                    if len(batch) >= max_batch:
                        result = client.execute(endpoint_name, {"items": batch})
                        row_results.append(result)
                        batch = []
                else:
                    result = client.execute(
                        endpoint_name, data, path_params={"id": record_id}
                    )
                    row_results.append({
                        "id": record_id,
                        "status": result.get("status", "error"),
                        "error": result.get("error"),
                    })

            # Flush remaining batch
            if is_bulk and batch:
                result = client.execute(endpoint_name, {"items": batch})
                row_results.append(result)

            succeeded = sum(1 for r in row_results if r.get("status") == "ok")
            failed = sum(1 for r in row_results if r.get("error"))

            return {
                "total_rows": len(changes),
                "api_calls": len(row_results),
                "succeeded": succeeded,
                "failed": failed,
                "details": row_results if failed > 0 else None,
            }

        elif operation == "INSERT" and preview:
            data = preview.get("data", {})
            if "raw_sql" not in data:
                result = client.execute(endpoint_name, data)
                return {
                    "total_rows": 1,
                    "api_calls": 1,
                    "succeeded": 1 if result.get("status") == "ok" else 0,
                    "failed": 1 if result.get("error") else 0,
                    "details": [result] if result.get("error") else None,
                }

        elif operation == "DELETE" and preview:
            rows_to_delete = preview.get("rows_to_delete", [])
            if not rows_to_delete:
                return None

            row_results = []
            for row in rows_to_delete:
                record_id = str(row.get("id", ""))
                if not record_id or record_id == "NULL":
                    row_results.append({"id": "unknown", "status": "error", "error": "No id field"})
                    continue
                result = client.execute(
                    endpoint_name, {}, path_params={"id": record_id}
                )
                row_results.append({
                    "id": record_id,
                    "status": result.get("status", "error"),
                    "error": result.get("error"),
                })

            succeeded = sum(1 for r in row_results if r.get("status") == "ok")
            failed = sum(1 for r in row_results if r.get("error"))

            return {
                "total_rows": len(rows_to_delete),
                "api_calls": len(row_results),
                "succeeded": succeeded,
                "failed": failed,
                "details": row_results if failed > 0 else None,
            }

        return None

    def _match_write_endpoint(
        self, client: Any, table: str, operation: str
    ) -> str | None:
        method_map = {
            "UPDATE": {"PUT", "PATCH"},
            "INSERT": {"POST"},
            "DELETE": {"DELETE"},
        }
        prefix_map = {
            "UPDATE": "update",
            "INSERT": "create",
            "DELETE": "delete",
        }
        target_methods = method_map.get(operation, {"POST"})
        op_prefix = prefix_map.get(operation, "create")

        # Priority 1: name contains table AND prefix
        for ep in client.write_endpoints:
            if table in ep["name"] and op_prefix in ep["name"]:
                return ep["name"]

        # Priority 2: name contains table AND method matches
        for ep in client.write_endpoints:
            if table in ep["name"] and ep.get("method", "POST").upper() in target_methods:
                return ep["name"]

        # Priority 3: singular form match (table "customers" → "delete_customer")
        table_singular = table[:-1] if table.endswith("s") else table
        for ep in client.write_endpoints:
            if table_singular in ep["name"] and op_prefix in ep["name"]:
                return ep["name"]

        # Priority 4: any endpoint with matching method
        for ep in client.write_endpoints:
            if ep.get("method", "POST").upper() in target_methods:
                return ep["name"]

        return None

    def _get_source_info(self, schema: str) -> dict[str, Any] | None:
        from dinobase.config import get_sources
        sources = get_sources()
        return sources.get(schema)


def get_endpoint_from_config(config: dict, name: str) -> dict | None:
    for ep in config.get("endpoints", []):
        if ep["name"] == name:
            return ep
    return None


# --- SQL parsing ---

def _split_statements(sql: str) -> list[str]:
    """Split multi-statement SQL on semicolons, ignoring empty strings."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def _validate_where_clause(where_clause: str) -> str | None:
    """Return an error string if the WHERE clause looks unsafe, else None."""
    if ";" in where_clause:
        return "WHERE clause may not contain semicolons"
    return None


def _parse_mutation_sql(sql: str) -> dict[str, Any]:
    stripped = sql.strip().rstrip(";")
    first_word = stripped.split()[0].upper() if stripped else ""

    if first_word in BLOCKED_STATEMENTS:
        return {"error": f"{first_word} statements are not allowed. Only UPDATE, INSERT, and DELETE are supported."}

    if first_word not in ("UPDATE", "INSERT", "DELETE"):
        return {"error": f"Not a mutation statement. Got '{first_word}', expected UPDATE, INSERT, or DELETE."}

    if first_word == "UPDATE":
        return _parse_update(stripped)
    if first_word == "DELETE":
        return _parse_delete(stripped)
    return _parse_insert(stripped)


def _parse_update(sql: str) -> dict[str, Any]:
    match = re.match(
        r'UPDATE\s+"?(\w+)"?\."?(\w+)"?\s+SET\s+(.+?)(?:\s+WHERE\s+(.+))?$',
        sql, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.match(
            r'UPDATE\s+"?(\w+)"?\s+SET\s+(.+?)(?:\s+WHERE\s+(.+))?$',
            sql, re.IGNORECASE | re.DOTALL,
        )
        if match:
            return {
                "operation": "UPDATE",
                "schema": "",
                "table": match.group(1),
                "set_clause": match.group(2).strip(),
                "where": match.group(3).strip() if match.group(3) else "",
                "error": "UPDATE requires schema.table format (e.g., crm.deals)",
            }
        return {"error": "Could not parse UPDATE statement. Use: UPDATE schema.table SET col = val WHERE condition"}

    return {
        "operation": "UPDATE",
        "schema": match.group(1),
        "table": match.group(2),
        "set_clause": match.group(3).strip(),
        "where": match.group(4).strip() if match.group(4) else "",
    }


def _parse_insert(sql: str) -> dict[str, Any]:
    match = re.match(
        r'INSERT\s+INTO\s+"?(\w+)"?\."?(\w+)"?\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)',
        sql, re.IGNORECASE,
    )
    if not match:
        match = re.match(
            r'INSERT\s+INTO\s+"?(\w+)"?\."?(\w+)"?\s+VALUES\s*\(([^)]+)\)',
            sql, re.IGNORECASE,
        )
        if match:
            return {
                "operation": "INSERT",
                "schema": match.group(1),
                "table": match.group(2),
                "columns": [],
                "values": [v.strip().strip("'\"") for v in match.group(3).split(",")],
            }
        return {"error": "Could not parse INSERT. Use: INSERT INTO schema.table (col1, col2) VALUES (val1, val2)"}

    return {
        "operation": "INSERT",
        "schema": match.group(1),
        "table": match.group(2),
        "columns": [c.strip().strip('"') for c in match.group(3).split(",")],
        "values": [v.strip().strip("'\"") for v in match.group(4).split(",")],
    }


def _parse_delete(sql: str) -> dict[str, Any]:
    match = re.match(
        r'DELETE\s+FROM\s+"?(\w+)"?\."?(\w+)"?(?:\s+WHERE\s+(.+))?$',
        sql, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return {"error": "Could not parse DELETE statement. Use: DELETE FROM schema.table WHERE condition"}

    where = match.group(3).strip() if match.group(3) else ""
    if not where:
        return {"error": "DELETE without WHERE clause is not allowed. Specify which rows to delete."}

    return {
        "operation": "DELETE",
        "schema": match.group(1),
        "table": match.group(2),
        "where": where,
    }


def _parse_set_clause(set_clause: str) -> dict[str, str]:
    changes = {}
    for part in set_clause.split(","):
        if "=" in part:
            col, val = part.split("=", 1)
            changes[col.strip().strip('"')] = val.strip().strip("'\"")
    return changes
