"""Query engine — executes SQL and formats results for agents."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from dinobase.db import DinobaseDB, META_SCHEMA


class QueryEngine:
    def __init__(self, db: DinobaseDB):
        self.db = db

    def execute(self, sql: str, max_rows: int = 200) -> dict[str, Any]:
        """Execute a SQL query and return formatted results.

        Mutations (UPDATE, INSERT, DELETE) are intercepted and routed to the
        mutation engine for preview/confirm flow. Use confirm() or --force to execute.

        Single-record lookups by primary key on stale sources are
        transparently resolved via live API calls when a YAML config exists.
        """
        # Route mutations to the mutation engine
        first_word = sql.strip().split()[0].upper() if sql.strip() else ""
        if first_word in ("UPDATE", "INSERT", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"):
            from dinobase.query.mutations import MutationEngine
            mutation_engine = MutationEngine(self.db)
            return mutation_engine.handle_sql(sql)

        # Check for live fetch opportunity before hitting parquet
        id_lookup = _detect_id_lookup(sql)
        if id_lookup:
            schema, table, record_id = id_lookup
            freshness = self.get_freshness(schema)
            if freshness.get("is_stale"):
                live_result = self._try_live_fetch(schema, table, record_id)
                if live_result is not None:
                    return live_result

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
            "_freshness": "synced",
        }

        if truncated:
            result["truncated"] = True
            result["message"] = (
                f"Showing {max_rows} of {total_rows} rows. "
                f"Use LIMIT N OFFSET M to paginate "
                f"(e.g., LIMIT {max_rows} OFFSET {max_rows} for page 2), "
                f"or add a WHERE clause to narrow results."
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

            # Get freshness info
            freshness = self.get_freshness(schema)

            source_entry: dict[str, Any] = {
                "name": schema,
                "tables": table_info,
                "table_count": len(user_tables),
                "total_rows": total_rows,
                "last_sync": freshness["last_sync"],
            }

            # Include freshness fields when threshold is set
            if freshness["threshold"] is not None:
                source_entry["age"] = freshness["age_human"]
                source_entry["freshness_threshold"] = freshness["threshold_human"]
                source_entry["is_stale"] = freshness["is_stale"]

            sources.append(source_entry)

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

        # Per-column KV metadata
        for entry in col_info:
            col_meta = self.db.get_metadata(schema, table, entry["name"])
            if col_meta:
                entry["metadata"] = col_meta

        # Include source freshness
        freshness = self.get_freshness(schema)
        result: dict[str, Any] = {
            "schema": schema,
            "table": table,
            "row_count": row_count,
            "columns": col_info,
            "last_sync": freshness["last_sync"],
        }

        # Table-level description and KV metadata
        table_desc = self.db.get_table_description(schema, table)
        if table_desc:
            result["description"] = table_desc
        table_meta = self.db.get_metadata(schema, table)
        if table_meta:
            result["metadata"] = table_meta
        if freshness["threshold"] is not None:
            result["age"] = freshness["age_human"]
            result["is_stale"] = freshness["is_stale"]

        # Enrich with pre-built relationship graph
        related = self.db.get_relationships(schema, table)
        if related:
            related_tables = []
            for r in related:
                if r["from_schema"] == schema and r["from_table"] == table:
                    other = f"{r['to_schema']}.{r['to_table']}"
                    join = f"ON {table}.{r['from_column']} = {r['to_table']}.{r['to_column']}"
                else:
                    other = f"{r['from_schema']}.{r['from_table']}"
                    join = f"ON {r['from_table']}.{r['from_column']} = {table}.{r['to_column']}"
                related_tables.append({
                    "table": other,
                    "join": join,
                    "cardinality": r["cardinality"],
                    "description": r["description"],
                })
            result["related_tables"] = related_tables

        return result

    def get_freshness(self, source_name: str) -> dict[str, Any]:
        """Return freshness info for a source.

        Returns {last_sync, age_seconds, age_human, threshold, threshold_human, is_stale}.
        """
        from dinobase.config import get_freshness_threshold

        sync_rows = self.db.query(
            f"SELECT MAX(finished_at) as last_sync FROM {META_SCHEMA}.sync_log "
            f"WHERE source_name = '{source_name}' AND status = 'success'"
        )

        last_sync = None
        if sync_rows and sync_rows[0]["last_sync"]:
            last_sync = sync_rows[0]["last_sync"]

        threshold = get_freshness_threshold(source_name)

        # File sources — never stale
        if threshold is None:
            return {
                "last_sync": str(last_sync) if last_sync else None,
                "age_seconds": None,
                "age_human": None,
                "threshold": None,
                "threshold_human": None,
                "is_stale": False,
            }

        # Compute age
        age_seconds = None
        is_stale = True  # No sync = stale
        if last_sync:
            if isinstance(last_sync, str):
                last_sync_dt = datetime.fromisoformat(last_sync)
            else:
                last_sync_dt = last_sync
            if last_sync_dt.tzinfo is None:
                last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_seconds = int((now - last_sync_dt).total_seconds())
            is_stale = age_seconds > threshold

        return {
            "last_sync": str(last_sync) if last_sync else None,
            "age_seconds": age_seconds,
            "age_human": _human_duration(age_seconds) if age_seconds is not None else None,
            "threshold": threshold,
            "threshold_human": _human_duration(threshold),
            "is_stale": is_stale,
        }

    def _try_live_fetch(
        self, schema: str, table: str, record_id: str
    ) -> dict[str, Any] | None:
        """Attempt to fetch a single record live from the source API.

        Returns a formatted result dict on success, None on any failure
        (falls back to parquet query).
        """
        from dinobase.config import get_sources

        sources = get_sources()
        source_config = sources.get(schema, {})
        source_type = source_config.get("type", schema)
        credentials = source_config.get("credentials", {})

        try:
            from dinobase.fetch.client import LiveFetchClient
            client = LiveFetchClient(source_type, credentials)
        except Exception:
            return None

        if not client.can_fetch(table):
            return None

        data = client.fetch_by_id(table, record_id)
        if data is None:
            return None

        # Normalize response to a flat dict (some APIs wrap in a key)
        if isinstance(data, dict):
            # Some APIs wrap: {"contact": {...}} — unwrap if single key matches table
            if len(data) == 1:
                key = next(iter(data))
                inner = data[key]
                if isinstance(inner, dict):
                    data = inner

        columns = list(data.keys())
        row = {col: _serialize(val) for col, val in data.items()}

        return {
            "columns": columns,
            "rows": [row],
            "row_count": 1,
            "total_rows": 1,
            "_freshness": "live",
            "_source": f"{source_type} API",
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


# ---------------------------------------------------------------------------
# SQL pattern detection for live fetch
# ---------------------------------------------------------------------------

# Matches: SELECT ... FROM ["]schema["].["]table["] WHERE ["]id["] = 'value'
# Also handles numeric values and double-quoted identifiers.
_ID_LOOKUP_RE = re.compile(
    r"""(?ix)                           # case-insensitive, verbose
    \bSELECT\b\s+.+?\s+               # SELECT ...
    \bFROM\b\s+                        # FROM
    "?(?P<schema>\w+)"?                # schema (optionally quoted)
    \s*\.\s*                           # dot
    "?(?P<table>\w+)"?                 # table (optionally quoted)
    \s+WHERE\s+                        # WHERE
    "?(?P<pk>\w+)"?\s*=\s*            # column = (the primary key)
    (?:                                # value: quoted string or number
        '(?P<val_str>[^']+)'           #   'string_value'
      | (?P<val_num>\d+)              #   numeric_value
    )
    \s*;?\s*$                          # optional semicolon, end
    """,
)


def _detect_id_lookup(sql: str) -> tuple[str, str, str] | None:
    """Detect simple single-record lookups: SELECT ... FROM schema.table WHERE id = 'value'.

    Only matches single-table SELECTs with a single equality condition.
    Returns (schema, table, id_value) or None.
    """
    # Quick rejection: must be a SELECT, no JOINs, no AND/OR
    normalized = sql.strip()
    upper = normalized.upper()
    if not upper.startswith("SELECT"):
        return None
    if " JOIN " in upper:
        return None
    if " AND " in upper or " OR " in upper:
        return None

    m = _ID_LOOKUP_RE.match(normalized)
    if not m:
        return None

    schema = m.group("schema")
    table = m.group("table")
    pk = m.group("pk")
    value = m.group("val_str") or m.group("val_num")

    # Only intercept if the WHERE column looks like a primary key
    if pk.lower() not in ("id", "pk", "uuid"):
        return None

    return (schema, table, value)


def _human_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m = seconds // 60
        return f"{m}m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if m:
        return f"{h}h {m}m"
    return f"{h}h"


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
