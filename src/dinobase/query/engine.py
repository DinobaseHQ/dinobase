"""Query engine — executes SQL and formats results for agents."""

from __future__ import annotations

import json
from typing import Any

from dinobase.db import DinobaseDB, META_SCHEMA


class QueryEngine:
    def __init__(self, db: DinobaseDB):
        self.db = db

    def execute(self, sql: str, max_rows: int = 200) -> dict[str, Any]:
        """Execute a SQL query and return formatted results.

        Mutations (UPDATE, INSERT) are intercepted and routed to the
        mutation engine for preview/confirm flow. Use confirm() to execute.
        """
        # Route mutations to the mutation engine
        first_word = sql.strip().split()[0].upper() if sql.strip() else ""
        if first_word in ("UPDATE", "INSERT", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"):
            from dinobase.query.mutations import MutationEngine
            mutation_engine = MutationEngine(self.db)
            return mutation_engine.handle_sql(sql)

        try:
            columns, rows = self.db.query_raw(sql)
        except Exception as e:
            return {"error": str(e)}

        total_rows = len(rows)
        truncated = total_rows > max_rows
        if truncated:
            rows = rows[:max_rows]

        # Convert rows to list of dicts, handling non-serializable types
        result_rows = []
        for row in rows:
            result_rows.append(
                {col: _serialize(val) for col, val in zip(columns, row)}
            )

        result: dict[str, Any] = {
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows),
            "total_rows": total_rows,
        }

        if truncated:
            result["truncated"] = True
            result["message"] = (
                f"Showing {max_rows} of {total_rows} rows. "
                f"Add LIMIT or a WHERE clause to narrow results."
            )

        return result

    def list_sources(self) -> dict[str, Any]:
        """List all connected data sources with their tables and stats."""
        schemas = self.db.get_schemas()
        sources: list[dict[str, Any]] = []

        for schema in schemas:
            if schema == META_SCHEMA:
                continue

            tables = self.db.get_tables(schema)
            user_tables = [t for t in tables if not t.startswith("_dlt_")]
            if not user_tables:
                continue

            total_rows = 0
            table_info = []
            for table in user_tables:
                count = self.db.get_row_count(schema, table)
                total_rows += count
                table_info.append({"name": table, "rows": count})

            # Get last sync time
            sync_rows = self.db.query(
                f"SELECT MAX(finished_at) as last_sync FROM {META_SCHEMA}.sync_log "
                f"WHERE source_name = '{schema}' AND status = 'success'"
            )
            last_sync = None
            if sync_rows and sync_rows[0]["last_sync"]:
                last_sync = str(sync_rows[0]["last_sync"])

            sources.append(
                {
                    "name": schema,
                    "tables": table_info,
                    "table_count": len(user_tables),
                    "total_rows": total_rows,
                    "last_sync": last_sync,
                }
            )

        return {"sources": sources}

    def describe_table(self, table_ref: str) -> dict[str, Any]:
        """Describe a table's columns. table_ref can be 'schema.table' or just 'table'."""
        parts = table_ref.split(".")
        if len(parts) == 2:
            schema, table = parts
        elif len(parts) == 1:
            # Try to find the table in any schema
            table = parts[0]
            schema = self._find_schema_for_table(table)
            if schema is None:
                return {"error": f"Table '{table}' not found in any schema"}
        else:
            return {"error": f"Invalid table reference: '{table_ref}'. Use 'schema.table' format."}

        columns = self.db.get_columns(schema, table)
        if not columns:
            # Try to suggest similar tables
            suggestion = self._suggest_table(table_ref)
            msg = f"Table '{table_ref}' not found."
            if suggestion:
                msg += f" Did you mean '{suggestion}'?"
            return {"error": msg}

        row_count = self.db.get_row_count(schema, table)

        # Get sample values
        sample_rows = []
        try:
            _, raw_rows = self.db.query_raw(
                f'SELECT * FROM "{schema}"."{table}" LIMIT 3'
            )
            col_names = [c["column_name"] for c in columns]
            for row in raw_rows:
                sample_rows.append(
                    {col: _serialize(val) for col, val in zip(col_names, row)}
                )
        except Exception:
            pass

        # Get annotations from _dinobase.columns
        annotations = self.db.get_column_annotations(schema, table)

        col_info = []
        for c in columns:
            col_name = c["column_name"]
            entry: dict[str, Any] = {
                "name": col_name,
                "type": c["data_type"],
                "nullable": c["is_nullable"] == "YES",
            }
            ann = annotations.get(col_name, {})
            if ann.get("description"):
                entry["description"] = ann["description"]
            if ann.get("note"):
                entry["note"] = ann["note"]
            col_info.append(entry)

        return {
            "schema": schema,
            "table": table,
            "row_count": row_count,
            "columns": col_info,
            "sample_rows": sample_rows,
        }

    def _find_schema_for_table(self, table: str) -> str | None:
        schemas = self.db.get_schemas()
        for schema in schemas:
            if schema == META_SCHEMA:
                continue
            tables = self.db.get_tables(schema)
            if table in tables:
                return schema
        return None

    def _suggest_table(self, table_ref: str) -> str | None:
        """Find the closest matching table name."""
        target = table_ref.lower().replace(".", "_")
        best = None
        best_score = 0

        for schema in self.db.get_schemas():
            if schema == META_SCHEMA:
                continue
            for table in self.db.get_tables(schema):
                if table.startswith("_dlt_"):
                    continue
                candidate = f"{schema}.{table}"
                # Simple substring match scoring
                score = 0
                if target in table.lower():
                    score = len(target) / len(table)
                elif table.lower() in target:
                    score = len(table) / len(target)
                if score > best_score:
                    best_score = score
                    best = candidate

        return best if best_score > 0.3 else None


def _serialize(val: Any) -> Any:
    """Make a value JSON-serializable."""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (list, dict)):
        return val
    # datetime, date, decimal, etc
    return str(val)
