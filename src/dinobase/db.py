"""DuckDB storage layer for Dinobase."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from dinobase.config import get_db_path

# Internal schema for dinobase metadata
META_SCHEMA = "_dinobase"

INIT_SQL = f"""
CREATE SCHEMA IF NOT EXISTS {META_SCHEMA};

CREATE SEQUENCE IF NOT EXISTS {META_SCHEMA}.sync_log_seq START 1;

CREATE TABLE IF NOT EXISTS {META_SCHEMA}.sync_log (
    id INTEGER PRIMARY KEY DEFAULT nextval('{META_SCHEMA}.sync_log_seq'),
    source_name VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL,
    started_at TIMESTAMP DEFAULT current_timestamp,
    finished_at TIMESTAMP,
    status VARCHAR DEFAULT 'running',
    tables_synced INTEGER DEFAULT 0,
    rows_synced BIGINT DEFAULT 0,
    error_message VARCHAR
);

CREATE TABLE IF NOT EXISTS {META_SCHEMA}.tables (
    source_name VARCHAR NOT NULL,
    schema_name VARCHAR NOT NULL,
    table_name VARCHAR NOT NULL,
    row_count BIGINT DEFAULT 0,
    last_sync TIMESTAMP,
    PRIMARY KEY (source_name, schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS {META_SCHEMA}.columns (
    source_name VARCHAR NOT NULL,
    schema_name VARCHAR NOT NULL,
    table_name VARCHAR NOT NULL,
    column_name VARCHAR NOT NULL,
    column_type VARCHAR,
    is_nullable BOOLEAN DEFAULT true,
    description VARCHAR,
    note VARCHAR,
    PRIMARY KEY (source_name, schema_name, table_name, column_name)
);

CREATE TABLE IF NOT EXISTS {META_SCHEMA}.live_rows (
    source_name VARCHAR NOT NULL,
    table_name VARCHAR NOT NULL,
    record_id VARCHAR NOT NULL,
    row_data JSON NOT NULL,
    written_at TIMESTAMP DEFAULT current_timestamp,
    mutation_id VARCHAR,
    PRIMARY KEY (source_name, table_name, record_id)
);

CREATE SEQUENCE IF NOT EXISTS {META_SCHEMA}.mutation_seq START 1;

CREATE TABLE IF NOT EXISTS {META_SCHEMA}.mutations (
    id INTEGER PRIMARY KEY DEFAULT nextval('{META_SCHEMA}.mutation_seq'),
    mutation_id VARCHAR NOT NULL UNIQUE,
    source_name VARCHAR NOT NULL,
    table_name VARCHAR NOT NULL,
    operation VARCHAR NOT NULL,
    sql_text VARCHAR NOT NULL,
    preview JSON,
    status VARCHAR DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT current_timestamp,
    confirmed_at TIMESTAMP,
    executed_at TIMESTAMP,
    result JSON,
    error_message VARCHAR
);
"""


class DinobaseDB:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = str(db_path or get_db_path())
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(self.db_path)
            self._init_metadata()
        return self._conn

    def _init_metadata(self) -> None:
        for statement in INIT_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                self._conn.execute(stmt)

    def execute(self, sql: str, params: list | None = None) -> duckdb.DuckDBPyRelation:
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Execute a query and return results as a list of dicts."""
        result = self.conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def query_raw(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Execute a query and return (column_names, rows)."""
        result = self.conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return columns, rows

    def get_schemas(self) -> list[str]:
        """List all user schemas (excluding internal ones)."""
        rows = self.query(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'main')"
        )
        return [r["schema_name"] for r in rows]

    def get_tables(self, schema: str) -> list[str]:
        """List all tables in a schema."""
        rows = self.query(
            f"SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' ORDER BY table_name"
        )
        return [r["table_name"] for r in rows]

    def get_columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        """Get column info for a table."""
        return self.query(
            f"SELECT column_name, data_type, is_nullable "
            f"FROM information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
            f"ORDER BY ordinal_position"
        )

    def get_row_count(self, schema: str, table: str) -> int:
        """Get row count for a table."""
        rows = self.query(f'SELECT COUNT(*) as cnt FROM "{schema}"."{table}"')
        return rows[0]["cnt"] if rows else 0

    def log_sync_start(self, source_name: str, source_type: str) -> int:
        """Record the start of a sync. Returns the sync log ID."""
        result = self.conn.execute(
            f"INSERT INTO {META_SCHEMA}.sync_log (source_name, source_type) "
            f"VALUES (?, ?) RETURNING id",
            [source_name, source_type],
        )
        return result.fetchone()[0]

    def log_sync_end(
        self,
        sync_id: int,
        status: str,
        tables_synced: int = 0,
        rows_synced: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Record the end of a sync."""
        self.conn.execute(
            f"UPDATE {META_SCHEMA}.sync_log "
            f"SET finished_at = current_timestamp, status = ?, "
            f"tables_synced = ?, rows_synced = ?, error_message = ? "
            f"WHERE id = ?",
            [status, tables_synced, rows_synced, error_message, sync_id],
        )

    def update_table_metadata(
        self,
        source_name: str,
        schema_name: str,
        annotations: dict[str, dict[str, dict[str, str]]] | None = None,
    ) -> None:
        """Refresh _dinobase.tables and _dinobase.columns from actual DuckDB schema.

        annotations: optional dict of {table_name: {column_name: {"description": ..., "note": ...}}}
        """
        annotations = annotations or {}
        tables = self.get_tables(schema_name)
        for table in tables:
            if table.startswith("_dlt_"):
                continue  # skip dlt internal tables
            row_count = self.get_row_count(schema_name, table)
            # Upsert into _dinobase.tables
            self.conn.execute(
                f"INSERT INTO {META_SCHEMA}.tables (source_name, schema_name, table_name, row_count, last_sync) "
                f"VALUES (?, ?, ?, ?, current_timestamp) "
                f"ON CONFLICT (source_name, schema_name, table_name) DO UPDATE SET "
                f"row_count = excluded.row_count, last_sync = excluded.last_sync",
                [source_name, schema_name, table, row_count],
            )
            # Update columns
            table_annotations = annotations.get(table, {})
            columns = self.get_columns(schema_name, table)
            for col in columns:
                col_name = col["column_name"]
                col_ann = table_annotations.get(col_name, {})
                self.conn.execute(
                    f"INSERT INTO {META_SCHEMA}.columns "
                    f"(source_name, schema_name, table_name, column_name, column_type, is_nullable, description, note) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    f"ON CONFLICT (source_name, schema_name, table_name, column_name) DO UPDATE SET "
                    f"column_type = excluded.column_type, is_nullable = excluded.is_nullable, "
                    f"description = COALESCE(excluded.description, {META_SCHEMA}.columns.description), "
                    f"note = COALESCE(excluded.note, {META_SCHEMA}.columns.note)",
                    [
                        source_name,
                        schema_name,
                        table,
                        col_name,
                        col["data_type"],
                        col["is_nullable"] == "YES",
                        col_ann.get("description"),
                        col_ann.get("note"),
                    ],
                )

    def get_column_annotations(self, schema_name: str, table_name: str) -> dict[str, dict[str, str | None]]:
        """Get annotations for all columns in a table. Returns {col_name: {description, note}}."""
        rows = self.query(
            f"SELECT column_name, description, note FROM {META_SCHEMA}.columns "
            f"WHERE schema_name = '{schema_name}' AND table_name = '{table_name}'"
        )
        return {
            r["column_name"]: {"description": r["description"], "note": r["note"]}
            for r in rows
            if r["description"] or r["note"]
        }

    def upsert_live_row(
        self,
        source_name: str,
        table_name: str,
        record_id: str,
        row_data: dict,
        mutation_id: str | None = None,
    ) -> None:
        """Store a recently-written row so it's immediately queryable.

        Live rows overlay the synced parquet data. They take priority in views
        and get cleared on the next full sync.
        """
        import json
        self.conn.execute(
            f"INSERT INTO {META_SCHEMA}.live_rows "
            f"(source_name, table_name, record_id, row_data, mutation_id) "
            f"VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT (source_name, table_name, record_id) DO UPDATE SET "
            f"row_data = excluded.row_data, written_at = current_timestamp, "
            f"mutation_id = excluded.mutation_id",
            [source_name, table_name, record_id, json.dumps(row_data, default=str), mutation_id],
        )

    def get_live_row_ids(self, source_name: str, table_name: str) -> list[str]:
        """Get IDs of all live rows for a source.table."""
        rows = self.query(
            f"SELECT record_id FROM {META_SCHEMA}.live_rows "
            f"WHERE source_name = '{source_name}' AND table_name = '{table_name}'"
        )
        return [r["record_id"] for r in rows]

    def clear_live_rows(self, source_name: str, table_name: str | None = None) -> int:
        """Clear live rows after a successful sync. Returns count cleared."""
        if table_name:
            sql = (
                f"DELETE FROM {META_SCHEMA}.live_rows "
                f"WHERE source_name = ? AND table_name = ?"
            )
            result = self.conn.execute(sql, [source_name, table_name])
        else:
            sql = f"DELETE FROM {META_SCHEMA}.live_rows WHERE source_name = ?"
            result = self.conn.execute(sql, [source_name])
        return result.fetchone()[0] if result.description else 0

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
