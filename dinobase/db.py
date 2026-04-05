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
    description VARCHAR,
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

CREATE TABLE IF NOT EXISTS {META_SCHEMA}.relationships (
    from_schema      VARCHAR NOT NULL,
    from_table       VARCHAR NOT NULL,
    from_column      VARCHAR NOT NULL,
    to_schema        VARCHAR NOT NULL,
    to_table         VARCHAR NOT NULL,
    to_column        VARCHAR NOT NULL,
    cardinality      VARCHAR NOT NULL DEFAULT 'one_to_many',
    confidence       FLOAT   NOT NULL DEFAULT 1.0,
    description      VARCHAR,
    detected_at      TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (from_schema, from_table, from_column,
                 to_schema,   to_table,   to_column)
);

CREATE TABLE IF NOT EXISTS {META_SCHEMA}.metadata (
    schema_name  VARCHAR NOT NULL,
    table_name   VARCHAR NOT NULL,
    column_name  VARCHAR NOT NULL DEFAULT '',
    key          VARCHAR NOT NULL,
    value        VARCHAR,
    PRIMARY KEY (schema_name, table_name, column_name, key)
);
"""


_META_TABLES = ["sync_log", "tables", "columns", "live_rows", "mutations", "relationships", "metadata"]


class DinobaseDB:
    def __init__(self, db_path: Path | str | None = None, storage_url: str | None = None):
        # Auto-detect cloud mode from config when no explicit args
        if storage_url is None and db_path is None:
            from dinobase.config import get_storage_config
            sc = get_storage_config()
            if sc["type"] != "local":
                storage_url = sc["url"]

        self.storage_url = storage_url
        self.is_cloud = storage_url is not None
        self.db_path = str(db_path or (":memory:" if self.is_cloud else get_db_path()))
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._metadata_loaded = False  # cloud metadata loaded lazily
        self._parquet_paths: dict[str, dict[str, str]] | None = None  # lazy path index

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            if self.is_cloud:
                self._conn = duckdb.connect(":memory:")
                self._setup_cloud()
            else:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                self._conn = duckdb.connect(self.db_path)
            self._init_metadata()
            # Cloud views and parquet paths are registered lazily on first query
            # to avoid S3 round trips on every DB init.
        return self._conn

    def _ensure_metadata_loaded(self) -> None:
        """Load cloud metadata tables from S3 if not yet done (lazy, one-time)."""
        if self.is_cloud and not self._metadata_loaded:
            self._load_cloud_metadata()
            self._metadata_loaded = True

    @property
    def meta_conn(self) -> duckdb.DuckDBPyConnection:
        """Like conn but guarantees cloud metadata tables are loaded.

        Use this in any method that reads or writes _dinobase.* tables.
        Plain SQL queries should use conn directly to avoid the S3 round trips.
        """
        c = self.conn
        self._ensure_metadata_loaded()
        return c

    def _setup_cloud(self) -> None:
        """Install DuckDB extensions and configure cloud credentials."""
        import os
        from dinobase.config import _storage_type_from_url

        storage_type = _storage_type_from_url(self.storage_url) if self.storage_url else "s3"

        if storage_type == "azure":
            self._setup_azure()
        else:
            self._setup_httpfs(storage_type)

    def _setup_httpfs(self, storage_type: str) -> None:
        """Configure httpfs for S3 or GCS."""
        import os

        self._conn.execute("INSTALL httpfs")
        self._conn.execute("LOAD httpfs")

        def _set(key: str, value: str) -> None:
            self._conn.execute(f"SET {key} = '{value.replace(chr(39), chr(39)*2)}'")

        if storage_type == "gcs":
            # GCS via S3-compatible interface — needs HMAC keys
            self._conn.execute("SET s3_endpoint = 'storage.googleapis.com'")
            if os.environ.get("GCS_HMAC_KEY_ID"):
                _set("s3_access_key_id", os.environ["GCS_HMAC_KEY_ID"])
            if os.environ.get("GCS_HMAC_SECRET"):
                _set("s3_secret_access_key", os.environ["GCS_HMAC_SECRET"])
        else:
            # S3
            if os.environ.get("AWS_ACCESS_KEY_ID"):
                _set("s3_access_key_id", os.environ["AWS_ACCESS_KEY_ID"])
            if os.environ.get("AWS_SECRET_ACCESS_KEY"):
                _set("s3_secret_access_key", os.environ["AWS_SECRET_ACCESS_KEY"])
            if os.environ.get("AWS_DEFAULT_REGION"):
                _set("s3_region", os.environ["AWS_DEFAULT_REGION"])
            elif os.environ.get("AWS_REGION"):
                _set("s3_region", os.environ["AWS_REGION"])
            # S3-compatible endpoints (MinIO, R2, etc.)
            if os.environ.get("S3_ENDPOINT"):
                _set("s3_endpoint", os.environ["S3_ENDPOINT"])
                self._conn.execute("SET s3_url_style = 'path'")

    def _setup_azure(self) -> None:
        """Configure Azure Blob Storage extension."""
        import os

        self._conn.execute("INSTALL azure")
        self._conn.execute("LOAD azure")

        def _set(key: str, value: str) -> None:
            self._conn.execute(f"SET {key} = '{value.replace(chr(39), chr(39)*2)}'")

        if os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):
            _set("azure_storage_connection_string", os.environ["AZURE_STORAGE_CONNECTION_STRING"])
        else:
            if os.environ.get("AZURE_STORAGE_ACCOUNT_NAME"):
                _set("azure_account_name", os.environ["AZURE_STORAGE_ACCOUNT_NAME"])
            if os.environ.get("AZURE_STORAGE_ACCOUNT_KEY"):
                _set("azure_account_key", os.environ["AZURE_STORAGE_ACCOUNT_KEY"])

    def _load_cloud_metadata(self) -> None:
        """Load metadata tables from cloud parquet files."""
        for table in _META_TABLES:
            url = f"{self.storage_url}_meta/{table}.parquet"
            try:
                self._conn.execute(
                    f"INSERT INTO {META_SCHEMA}.{table} "
                    f"SELECT * FROM read_parquet('{url}') "
                    f"ON CONFLICT DO NOTHING"
                )
            except Exception as e:
                if "does not exist" not in str(e).lower() and "no such file" not in str(e).lower():
                    import sys
                    print(f"[dinobase] Warning: could not load metadata table '{table}': {e}", file=sys.stderr)

    def _discover_table_parquet_paths(self, source_name: str) -> dict[str, str]:
        """Scan cloud storage to find parquet paths for all tables in a source.

        Returns {table_name: parquet_glob_url}.  Handles the dlt filesystem
        layout where tables live one level deeper under a schema subdirectory
        (e.g. data/{source}/{dlt_schema}/{table}/*.parquet).
        """
        from dinobase.cloud import CloudStorage

        cloud = CloudStorage(self.storage_url)
        data_fs_path = cloud._to_fs_path(f"{self.storage_url}data/{source_name}")
        result: dict[str, str] = {}
        _SKIP = {"init"}
        try:
            level1 = cloud.fs.ls(data_fs_path, detail=False)
            for entry in level1:
                entry_name = entry.rstrip("/").split("/")[-1]
                if entry_name.startswith("_dlt_") or entry_name in _SKIP:
                    continue
                try:
                    children = cloud.fs.ls(entry, detail=False)
                except Exception:
                    continue
                has_parquet = any(c.endswith(".parquet") for c in children)
                if has_parquet:
                    # entry is a table directory directly
                    result[entry_name] = (
                        f"{self.storage_url}data/{source_name}/{entry_name}/*.parquet"
                    )
                else:
                    # entry is a dlt schema subdirectory containing table dirs
                    schema_dir = entry_name
                    for child in children:
                        table_name = child.rstrip("/").split("/")[-1]
                        if table_name.startswith("_dlt_") or table_name.startswith("_live_"):
                            continue
                        result[table_name] = (
                            f"{self.storage_url}data/{source_name}"
                            f"/{schema_dir}/{table_name}/*.parquet"
                        )
        except (FileNotFoundError, OSError):
            pass
        return result

    def _ensure_parquet_paths_loaded(self) -> None:
        """Load parquet path index from cloud into memory (one S3 call, cached).

        Also creates DuckDB schemas for all known sources so queries can
        reference them even before the individual views are registered.
        """
        if self._parquet_paths is not None:
            return
        from dinobase.cloud import CloudStorage
        cloud = CloudStorage(self.storage_url)
        self._parquet_paths = (
            cloud.read_json(f"{self.storage_url}_meta/parquet_paths.json") or {}
        )
        # Create schemas so schema-qualified queries don't get "Schema does not exist"
        for source_name in self._parquet_paths:
            self.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{source_name}"')

    def register_view_on_demand(self, source_name: str, table_name: str) -> bool:
        """Create a DuckDB view for source_name.table_name on first access.

        Called transparently by QueryEngine when a query references a table
        whose view hasn't been created yet.  Returns True on success.
        """
        self._ensure_parquet_paths_loaded()
        parquet_glob = self._parquet_paths.get(source_name, {}).get(table_name)
        if not parquet_glob:
            # Table not in saved index — try a live S3 scan as fallback
            discovered = self._discover_table_parquet_paths(source_name)
            parquet_glob = discovered.get(table_name)
            if parquet_glob:
                self._parquet_paths.setdefault(source_name, {})[table_name] = parquet_glob
        if not parquet_glob:
            return False
        try:
            self.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{source_name}"')
            self.conn.execute(
                f'CREATE OR REPLACE VIEW "{source_name}"."{table_name}" AS '
                f"SELECT * FROM read_parquet('{parquet_glob}')"
            )
            return True
        except Exception as e:
            import sys
            print(
                f"[dinobase] register_view_on_demand failed for "
                f"{source_name}.{table_name}: {e}",
                file=sys.stderr,
            )
            return False

    def _register_cloud_views(self) -> None:
        """Eagerly register all views (e.g. after a sync or explicit refresh).

        For normal query serving, views are created lazily via
        register_view_on_demand() instead.
        """
        self._ensure_parquet_paths_loaded()
        for source_name, table_globs in (self._parquet_paths or {}).items():
            for table_name in table_globs:
                self.register_view_on_demand(source_name, table_name)

    def save_parquet_paths(self, source_name: str, paths: dict[str, str]) -> None:
        """Persist discovered parquet paths and update the in-memory index."""
        from dinobase.cloud import CloudStorage
        cloud = CloudStorage(self.storage_url)
        url = f"{self.storage_url}_meta/parquet_paths.json"
        all_paths: dict[str, dict[str, str]] = cloud.read_json(url) or {}
        all_paths[source_name] = paths
        cloud.write_json(url, all_paths)
        # Keep the in-memory cache consistent so subsequent requests see new tables
        if self._parquet_paths is None:
            self._parquet_paths = all_paths
        else:
            self._parquet_paths[source_name] = paths

    def save_cloud_metadata(self) -> None:
        """Persist metadata tables to cloud storage as parquet files."""
        if not self.is_cloud or self._conn is None:
            return
        for table in _META_TABLES:
            self._save_meta_table(table)

    def _save_meta_table(self, table: str) -> None:
        """Save a single metadata table to cloud parquet."""
        url = f"{self.storage_url}_meta/{table}.parquet"
        try:
            self._conn.execute(
                f"COPY (SELECT * FROM {META_SCHEMA}.{table}) "
                f"TO '{url}' (FORMAT PARQUET)"
            )
        except Exception as e:
            import sys
            print(f"[cloud] failed to save {table}: {e}", file=sys.stderr)

    def _init_metadata(self) -> None:
        for statement in INIT_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                self._conn.execute(stmt)
        # Migrations for existing DBs
        self._conn.execute(
            f"ALTER TABLE {META_SCHEMA}.tables ADD COLUMN IF NOT EXISTS description VARCHAR"
        )

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
        res = self.conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = ? ORDER BY table_name",
            [schema],
        )
        return [row[0] for row in res.fetchall()]

    def get_columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        """Get column info for a table."""
        res = self.conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? "
            "ORDER BY ordinal_position",
            [schema, table],
        )
        cols = [d[0] for d in res.description]
        return [dict(zip(cols, row)) for row in res.fetchall()]

    def get_row_count(self, schema: str, table: str) -> int:
        """Get row count for a table."""
        rows = self.query(f'SELECT COUNT(*) as cnt FROM "{schema}"."{table}"')
        return rows[0]["cnt"] if rows else 0

    def log_sync_start(self, source_name: str, source_type: str) -> int:
        """Record the start of a sync. Returns the sync log ID."""
        result = self.meta_conn.execute(
            f"INSERT INTO {META_SCHEMA}.sync_log (source_name, source_type) "
            f"VALUES (?, ?) "
            f"RETURNING id",
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
        self.meta_conn.execute(
            f"UPDATE {META_SCHEMA}.sync_log "
            f"SET finished_at = current_timestamp, status = ?, "
            f"tables_synced = ?, rows_synced = ?, error_message = ? "
            f"WHERE id = ?",
            [status, tables_synced, rows_synced, error_message, sync_id],
        )
        if self.is_cloud:
            self._save_meta_table("sync_log")

    def update_table_metadata(
        self,
        source_name: str,
        schema_name: str,
        annotations: dict[str, dict[str, dict[str, str]]] | None = None,
        row_counts: dict[str, int] | None = None,
        override_tables: list[str] | None = None,
    ) -> None:
        """Refresh _dinobase.tables and _dinobase.columns from actual DuckDB schema.

        annotations: optional dict of {table_name: {column_name: {"description": ..., "note": ...}}}
        row_counts: optional pre-computed row counts; when provided, skips SELECT COUNT(*) per table
        override_tables: explicit table list; when provided, skips information_schema.tables query
                         (which requires DuckDB views to exist).
        """
        from collections import defaultdict
        annotations = annotations or {}
        if override_tables is not None:
            tables_to_update = [t for t in override_tables if not t.startswith("_dlt_")]
        else:
            tables = self.get_tables(schema_name)
            tables_to_update = [t for t in tables if not t.startswith("_dlt_")]

        # Use stored column schemas from _dinobase.columns as the primary source.
        # information_schema.columns for DuckDB views backed by read_parquet() causes
        # DuckDB to resolve each view's schema against S3 — one footer read per table.
        # The stored schemas come from the previous sync and avoid all S3 access.
        # For tables that have no stored schema yet (first sync), fall back to
        # information_schema.columns which will read S3 (unavoidable on first sync).
        stored_cols = self.get_stored_column_schemas(source_name, schema_name)
        columns_by_table: dict[str, list[dict]] = defaultdict(list)
        for tbl, col_list in stored_cols.items():
            for col_name, col_type in col_list:
                columns_by_table[tbl].append({
                    "column_name": col_name,
                    "data_type": col_type,
                    "is_nullable": "YES",  # conservative default for stored schema
                })

        # For tables missing from stored schemas (new tables this sync), read from
        # information_schema.columns — triggers S3 reads for those tables only.
        new_tables = [t for t in tables_to_update if not columns_by_table.get(t)]
        if new_tables:
            try:
                res = self.conn.execute(
                    "SELECT table_name, column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = ? AND table_name = ANY(?) "
                    "ORDER BY table_name, ordinal_position",
                    [schema_name, new_tables],
                )
                for row in res.fetchall():
                    columns_by_table[row[0]].append({
                        "column_name": row[1],
                        "data_type": row[2],
                        "is_nullable": row[3],
                    })
            except Exception:
                pass

        for table in tables_to_update:
            # Use pre-computed row count when available to avoid SELECT COUNT(*) over S3
            if row_counts is not None:
                row_count = row_counts.get(table, 0)
            else:
                row_count = self.get_row_count(schema_name, table)
            # Upsert into _dinobase.tables
            self.meta_conn.execute(
                f"INSERT INTO {META_SCHEMA}.tables (source_name, schema_name, table_name, row_count, last_sync) "
                f"VALUES (?, ?, ?, ?, current_timestamp) "
                f"ON CONFLICT (source_name, schema_name, table_name) DO UPDATE SET "
                f"row_count = excluded.row_count, last_sync = excluded.last_sync",
                [source_name, schema_name, table, row_count],
            )
            # Update columns (stored schemas first, fall back to per-table query)
            table_annotations = annotations.get(table, {})
            columns = columns_by_table.get(table) or self.get_columns(schema_name, table)
            for col in columns:
                col_name = col["column_name"]
                col_ann = table_annotations.get(col_name, {})
                self.meta_conn.execute(
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
        if self.is_cloud:
            self._save_meta_table("tables")
            self._save_meta_table("columns")

    def get_stored_column_schemas(
        self, source_name: str, schema_name: str
    ) -> dict[str, list[tuple[str, str]]]:
        """Return stored column (name, type) pairs per table from _dinobase.columns.

        Used by register_cloud_source to recreate staging tables from stored schema
        without reading S3 parquet files — avoids one S3 footer read per table.
        Returns {table_name: [(col_name, col_type), ...]} for all known tables.
        """
        try:
            rows = self.meta_conn.execute(
                f"SELECT table_name, column_name, column_type "
                f"FROM {META_SCHEMA}.columns "
                "WHERE source_name = ? AND schema_name = ? "
                "AND column_type IS NOT NULL "
                "ORDER BY table_name, column_name",
                [source_name, schema_name],
            ).fetchall()
        except Exception:
            return {}
        result: dict[str, list[tuple[str, str]]] = {}
        for table_name, col_name, col_type in rows:
            result.setdefault(table_name, []).append((col_name, col_type))
        return result

    def get_column_annotations(self, schema_name: str, table_name: str) -> dict[str, dict[str, str | None]]:
        """Get annotations for all columns in a table. Returns {col_name: {description, note}}."""
        result = self.meta_conn.execute(
            f"SELECT column_name, description, note FROM {META_SCHEMA}.columns "
            "WHERE schema_name = ? AND table_name = ?",
            [schema_name, table_name],
        )
        return {
            r[0]: {"description": r[1], "note": r[2]}
            for r in result.fetchall()
            if r[1] or r[2]
        }

    def upsert_relationship(
        self,
        from_schema: str,
        from_table: str,
        from_column: str,
        to_schema: str,
        to_table: str,
        to_column: str,
        cardinality: str = "one_to_many",
        confidence: float = 1.0,
        description: str = "",
    ) -> None:
        """Store or update a relationship edge between two tables."""
        self.meta_conn.execute(
            f"INSERT INTO {META_SCHEMA}.relationships "
            f"(from_schema, from_table, from_column, to_schema, to_table, to_column, "
            f"cardinality, confidence, description) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            f"ON CONFLICT (from_schema, from_table, from_column, to_schema, to_table, to_column) "
            f"DO UPDATE SET cardinality = excluded.cardinality, confidence = excluded.confidence, "
            f"description = excluded.description",
            [from_schema, from_table, from_column, to_schema, to_table, to_column,
             cardinality, confidence, description],
        )
        if self.is_cloud:
            self._save_meta_table("relationships")

    def get_relationships(self, schema: str, table: str) -> list[dict[str, Any]]:
        """Get all relationships where this table appears on either side, ordered by confidence."""
        result = self.meta_conn.execute(
            f"SELECT from_schema, from_table, from_column, to_schema, to_table, to_column, "
            f"cardinality, confidence, description "
            f"FROM {META_SCHEMA}.relationships "
            f"WHERE (from_schema = ? AND from_table = ?) OR (to_schema = ? AND to_table = ?) "
            f"ORDER BY confidence DESC",
            [schema, table, schema, table],
        )
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def purge_relationships(self, schema: str) -> int:
        """Delete edges where either endpoint table no longer exists in the schema."""
        result = self.meta_conn.execute(
            f"DELETE FROM {META_SCHEMA}.relationships "
            f"WHERE (from_schema = ? AND from_table NOT IN ("
            f"  SELECT table_name FROM information_schema.tables WHERE table_schema = ?)) "
            f"OR (to_schema = ? AND to_table NOT IN ("
            f"  SELECT table_name FROM information_schema.tables WHERE table_schema = ?))",
            [schema, schema, schema, schema],
        )
        count = result.fetchone()[0] if result.description else 0
        if self.is_cloud and count > 0:
            self._save_meta_table("relationships")
        return count

    def has_relationships(self, schema: str) -> bool:
        """Return True if this schema has any relationship edges."""
        row = self.meta_conn.execute(
            f"SELECT COUNT(*) FROM {META_SCHEMA}.relationships "
            f"WHERE from_schema = ? OR to_schema = ?",
            [schema, schema],
        ).fetchone()
        return (row[0] if row else 0) > 0

    def get_sources_without_relationships(self) -> list[str]:
        """Return schema names that have tables but no relationship edges."""
        self._ensure_metadata_loaded()
        all_sources = self.query(
            f"SELECT DISTINCT schema_name FROM {META_SCHEMA}.tables "
            f"WHERE schema_name != '{META_SCHEMA}'"
        )
        result = []
        for row in all_sources:
            schema = row["schema_name"]
            if not self.has_relationships(schema):
                result.append(schema)
        return result

    def set_table_description(self, schema: str, table: str, description: str) -> None:
        """Set the human-readable description for a table."""
        self.meta_conn.execute(
            f"UPDATE {META_SCHEMA}.tables SET description = ? "
            f"WHERE schema_name = ? AND table_name = ?",
            [description, schema, table],
        )
        if self.is_cloud:
            self._save_meta_table("tables")

    def get_table_description(self, schema: str, table: str) -> str | None:
        """Return the description for a table, or None if not set."""
        row = self.meta_conn.execute(
            f"SELECT description FROM {META_SCHEMA}.tables "
            f"WHERE schema_name = ? AND table_name = ?",
            [schema, table],
        ).fetchone()
        return row[0] if row else None

    def set_metadata(
        self, schema: str, table: str, key: str, value: str, column: str = ""
    ) -> None:
        """Upsert a key-value metadata tag for a table (column='') or column."""
        self.meta_conn.execute(
            f"INSERT INTO {META_SCHEMA}.metadata "
            f"(schema_name, table_name, column_name, key, value) "
            f"VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT (schema_name, table_name, column_name, key) "
            f"DO UPDATE SET value = excluded.value",
            [schema, table, column, key, value],
        )
        if self.is_cloud:
            self._save_meta_table("metadata")

    def get_metadata(
        self, schema: str, table: str, column: str = ""
    ) -> dict[str, str]:
        """Return all KV metadata tags for a table or column as {key: value}."""
        rows = self.meta_conn.execute(
            f"SELECT key, value FROM {META_SCHEMA}.metadata "
            f"WHERE schema_name = ? AND table_name = ? AND column_name = ?",
            [schema, table, column],
        ).fetchall()
        return {row[0]: row[1] for row in rows}

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
        self.meta_conn.execute(
            f"INSERT INTO {META_SCHEMA}.live_rows "
            f"(source_name, table_name, record_id, row_data, mutation_id) "
            f"VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT (source_name, table_name, record_id) DO UPDATE SET "
            f"row_data = excluded.row_data, written_at = current_timestamp, "
            f"mutation_id = excluded.mutation_id",
            [source_name, table_name, record_id, json.dumps(row_data, default=str), mutation_id],
        )
        if self.is_cloud:
            self._save_meta_table("live_rows")

    def get_live_row_ids(self, source_name: str, table_name: str) -> list[str]:
        """Get IDs of all live rows for a source.table."""
        result = self.meta_conn.execute(
            f"SELECT record_id FROM {META_SCHEMA}.live_rows "
            "WHERE source_name = ? AND table_name = ?",
            [source_name, table_name],
        )
        return [r[0] for r in result.fetchall()]

    def clear_live_rows(self, source_name: str, table_name: str | None = None) -> int:
        """Clear live rows after a successful sync. Returns count cleared."""
        if table_name:
            sql = (
                f"DELETE FROM {META_SCHEMA}.live_rows "
                f"WHERE source_name = ? AND table_name = ?"
            )
            result = self.meta_conn.execute(sql, [source_name, table_name])
        else:
            sql = f"DELETE FROM {META_SCHEMA}.live_rows WHERE source_name = ?"
            result = self.meta_conn.execute(sql, [source_name])
        count = result.fetchone()[0] if result.description else 0
        if self.is_cloud:
            self._save_meta_table("live_rows")
        return count

    def close(self) -> None:
        if self._conn is not None:
            self.save_cloud_metadata()
            self._conn.close()

    def __enter__(self) -> "DinobaseDB":
        return self

    def __exit__(self, *_) -> None:
        self.close()
