"""Sync engine — wraps dlt to load data from sources into DuckDB."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import dlt

from dinobase.db import DinobaseDB


@dataclass
class SyncResult:
    source_name: str
    source_type: str
    tables_synced: int
    rows_synced: int
    status: str
    error: str | None = None


class SyncEngine:
    def __init__(self, db: DinobaseDB):
        self.db = db

    def sync(self, source_name: str, source_config: dict[str, Any]) -> SyncResult:
        """Sync a single source into DuckDB."""
        source_type = source_config["type"]
        credentials = source_config.get("credentials", {})

        # Refresh OAuth tokens if expired
        from dinobase.auth import ensure_fresh_credentials
        credentials = ensure_fresh_credentials(source_name, source_type, credentials)

        # Distributed lock for cloud mode
        cloud = None
        if self.db.is_cloud:
            from dinobase.cloud import CloudStorage
            cloud = CloudStorage(self.db.storage_url)
            if not cloud.acquire_lock(source_name):
                return SyncResult(
                    source_name=source_name,
                    source_type=source_type,
                    tables_synced=0,
                    rows_synced=0,
                    status="skipped",
                    error="Another process is syncing this source",
                )

        sync_id = self.db.log_sync_start(source_name, source_type)

        try:
            result = self._run_pipeline(source_name, source_type, credentials)

            # Extract metadata from the source API (descriptions, enums, etc.)
            synced_tables = [
                t for t in self.db.get_tables(source_name)
                if not t.startswith("_dlt_")
            ]
            from dinobase.sync.sources import extract_metadata
            annotations = extract_metadata(source_type, credentials, synced_tables)

            self.db.update_table_metadata(source_name, source_name, annotations=annotations)

            # Clear live/staging rows — parquet is now fresh
            self.db.clear_live_rows(source_name)
            for t in synced_tables:
                staging = f"_live_{t}"
                if staging in self.db.get_tables(source_name):
                    try:
                        self.db.conn.execute(f'DELETE FROM "{source_name}"."{staging}"')
                    except Exception:
                        pass

            self.db.log_sync_end(
                sync_id,
                status="success",
                tables_synced=result.tables_synced,
                rows_synced=result.rows_synced,
            )
            from dinobase.semantic_agent import spawn_semantic_agent
            spawn_semantic_agent(source_name)
            return result
        except Exception as e:
            error_msg = str(e)
            self.db.log_sync_end(sync_id, status="error", error_message=error_msg)
            return SyncResult(
                source_name=source_name,
                source_type=source_type,
                tables_synced=0,
                rows_synced=0,
                status="error",
                error=error_msg,
            )
        finally:
            if cloud:
                cloud.release_lock(source_name)

    def _run_pipeline(
        self, source_name: str, source_type: str, credentials: dict[str, str],
        resource_names: list[str] | None = None,
    ) -> SyncResult:
        from dinobase.sync.sources import get_source

        dlt_source = get_source(source_type, credentials, resource_names=resource_names)

        # Choose destination based on storage mode
        pipeline_kwargs: dict = {}
        if self.db.is_cloud:
            import tempfile
            pipelines_dir = tempfile.mkdtemp(prefix="dinobase_")

            # Restore previous pipeline state from cloud for incremental sync
            self._restore_pipeline_state(source_name, pipelines_dir)

            destination = dlt.destinations.filesystem(
                bucket_url=self.db.storage_url + "data/",
                layout="{schema_name}/{table_name}/{load_id}.{file_id}.{ext}",
            )
            pipeline_kwargs["pipelines_dir"] = pipelines_dir
        else:
            destination = dlt.destinations.duckdb(self.db.db_path)
            import os as _os
            _pipelines_dir = _os.path.join(_os.path.dirname(self.db.db_path), "_pipelines")
            _os.makedirs(_pipelines_dir, exist_ok=True)
            pipeline_kwargs["pipelines_dir"] = _pipelines_dir

        pipeline = dlt.pipeline(
            pipeline_name=f"dinobase_{source_name}",
            destination=destination,
            dataset_name=source_name,
            progress="log",
            **pipeline_kwargs,
        )

        print(f"Syncing {source_name} ({source_type})...", file=sys.stderr)
        _skip_tables: list[str] = []
        _max_retries = 5  # guard against infinite loops if every table is broken
        for _attempt in range(_max_retries):
            try:
                _run_kwargs: dict = {}
                if not self.db.is_cloud:
                    # Use parquet staging to avoid INSERT VALUES SQL escaping issues
                    # (e.g. strings with percent signs or special chars cause DuckDB parse errors)
                    _run_kwargs["loader_file_format"] = "parquet"
                load_info = pipeline.run(dlt_source, **_run_kwargs)
                break  # success
            except Exception as _e:
                # If the load fails because of an INT64/INT128 schema conflict
                # (e.g. ClickHouse UInt64 values that overflow DuckDB INT64, or a
                # previously-cached dlt schema that typed UInt64 as INT64 while
                # type_adapter_callback now says "text"), recover by:
                #   1. Dropping the DuckDB schema via the already-open connection
                #      (pipeline.drop() opens a NEW connection which DuckDB may reject
                #      when the file already has an open read-write connection, causing
                #      it to silently skip the dataset drop).
                #   2. Dropping the local dlt state (pipeline.drop()).
                #   3. Retrying from scratch so fresh tables are created with the
                #      correct VARCHAR types.
                _emsg = str(_e)
                _is_int64_conflict = (
                    "INT128" in _emsg
                    or ("out of range for the destination type" in _emsg and "INT64" in _emsg)
                    or ("Could not convert" in _emsg and "INT64" in _emsg)
                )
                # ClickHouse Code 47: UNKNOWN_IDENTIFIER — typically means an EPHEMERAL
                # column (or an ALIAS whose expression references one) was included in
                # the SELECT. Recover by dropping the failing table from the resource
                # list and retrying so the rest of the source syncs successfully.
                _is_unknown_identifier = (
                    "UNKNOWN_IDENTIFIER" in _emsg
                    or ("Code: 47" in _emsg)
                )
                if _is_int64_conflict:
                    print(
                        f"  [schema-reset] INT64 schema conflict — dropping stale schema "
                        f"and retrying {source_name} from scratch.",
                        file=sys.stderr,
                    )
                    # Step 1: drop DuckDB schema using the already-open connection
                    if not self.db.is_cloud:
                        try:
                            self.db.conn.execute(
                                f'DROP SCHEMA IF EXISTS "{source_name}" CASCADE'
                            )
                        except Exception as _drop_err:
                            print(
                                f"  [schema-reset] DROP SCHEMA failed: {_drop_err}",
                                file=sys.stderr,
                            )
                    # Step 2: clear local dlt state (schema files, pipeline state)
                    pipeline.drop()
                    # Step 3: re-get the source (iterators exhausted after failed run)
                    dlt_source = get_source(
                        source_type, credentials, resource_names=resource_names
                    )
                elif _is_unknown_identifier and source_type == "clickhouse":
                    import re as _re
                    # Parse the failing table name from the error:
                    #   "In processing pipe `sharded_events`"  OR
                    #   "extraction of resource `sharded_events`"
                    _match = (
                        _re.search(r"processing pipe `([^`]+)`", _emsg)
                        or _re.search(r"resource `([^`]+)`", _emsg)
                    )
                    if _match:
                        _bad_table = _match.group(1)
                        if _bad_table in _skip_tables:
                            # Already tried skipping this table — give up
                            raise
                        _skip_tables.append(_bad_table)
                        print(
                            f"  [ephemeral-skip] ClickHouse UNKNOWN_IDENTIFIER on "
                            f"'{_bad_table}' — skipping table and retrying "
                            f"({len(_skip_tables)} skipped so far).",
                            file=sys.stderr,
                        )
                        pipeline.drop()
                        dlt_source = get_source(
                            source_type, credentials,
                            resource_names=resource_names,
                            extra_skip_tables=list(_skip_tables),
                        )
                    else:
                        raise
                else:
                    raise
        else:
            raise RuntimeError(
                f"Sync of {source_name} failed after {_max_retries} attempts. "
                f"Last error: {_emsg}"
            )

        if self.db.is_cloud:
            # Save pipeline state to cloud for next incremental sync
            self._save_pipeline_state(source_name, pipelines_dir)

            if load_info.loads_ids:
                result = self._register_cloud_source(source_name, source_type, load_info)
                # Compact parquet files after registration
                self._compact_source(source_name, result)
                return result

            return SyncResult(
                source_name=source_name,
                source_type=source_type,
                tables_synced=0,
                rows_synced=0,
                status="success",
            )

        # Count tables and rows from load info (local mode)
        tables_synced = 0
        rows_synced = 0
        if load_info.loads_ids:
            # Query the dataset to count what was loaded
            tables = self.db.get_tables(source_name)
            tables_synced = len([t for t in tables if not t.startswith("_dlt_")])
            for table in tables:
                if not table.startswith("_dlt_"):
                    rows_synced += self.db.get_row_count(source_name, table)

        return SyncResult(
            source_name=source_name,
            source_type=source_type,
            tables_synced=tables_synced,
            rows_synced=rows_synced,
            status="success",
        )

    def _register_cloud_source(
        self, source_name: str, source_type: str, load_info: Any,
    ) -> SyncResult:
        """After cloud sync, create DuckDB views over the written parquet files."""
        # Discover tables from load_info
        table_names: set[str] = set()
        for package in load_info.load_packages:
            for job in package.jobs.get("completed_jobs", []):
                # Job file info contains table name
                parts = job.file_path.split("/") if hasattr(job, "file_path") else []
                if parts:
                    table_names.add(job.table_name if hasattr(job, "table_name") else parts[-2])

        # Fallback: try to get table names from load_info metrics
        if not table_names:
            try:
                for package in load_info.load_packages:
                    for table_name in package.schema.tables:
                        if not table_name.startswith("_dlt_"):
                            table_names.add(table_name)
            except Exception:
                pass

        self.db.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{source_name}"')

        tables_synced = 0
        rows_synced = 0

        for table_name in table_names:
            if table_name.startswith("_dlt_"):
                continue

            parquet_glob = f"{self.db.storage_url}data/{source_name}/{table_name}/*.parquet"
            staging_table = f"_live_{table_name}"

            try:
                # Create empty staging table with parquet schema
                self.db.conn.execute(
                    f'CREATE TABLE IF NOT EXISTS "{source_name}"."{staging_table}" '
                    f"AS SELECT * FROM read_parquet('{parquet_glob}') WHERE false"
                )
                # Create view merging parquet + staging
                self.db.conn.execute(
                    f'CREATE OR REPLACE VIEW "{source_name}"."{table_name}" AS '
                    f'SELECT * FROM "{source_name}"."{staging_table}" '
                    f"UNION ALL "
                    f"SELECT * FROM read_parquet('{parquet_glob}') "
                    f"WHERE CAST(id AS VARCHAR) NOT IN ("
                    f'  SELECT CAST(id AS VARCHAR) FROM "{source_name}"."{staging_table}"'
                    f")"
                )
                row_count = self.db.get_row_count(source_name, table_name)
                tables_synced += 1
                rows_synced += row_count
            except Exception as e:
                print(f"  [cloud] failed to register {source_name}.{table_name}: {e}", file=sys.stderr)

        return SyncResult(
            source_name=source_name,
            source_type=source_type,
            tables_synced=tables_synced,
            rows_synced=rows_synced,
            status="success",
        )

    # ------------------------------------------------------------------
    # Pipeline state persistence (incremental sync support)
    # ------------------------------------------------------------------

    def _restore_pipeline_state(self, source_name: str, pipelines_dir: str) -> None:
        """Download dlt pipeline state from cloud for incremental sync."""
        from dinobase.cloud import CloudStorage

        cloud = CloudStorage(self.db.storage_url)
        state_url = f"{self.db.storage_url}_state/dinobase_{source_name}/"
        local_state_dir = f"{pipelines_dir}/dinobase_{source_name}"

        count = cloud.download_dir(state_url, local_state_dir)
        if count > 0:
            print(f"  [state] restored pipeline state ({count} files)", file=sys.stderr)

    def _save_pipeline_state(self, source_name: str, pipelines_dir: str) -> None:
        """Upload dlt pipeline state to cloud for next incremental sync."""
        from pathlib import Path
        from dinobase.cloud import CloudStorage

        local_state_dir = f"{pipelines_dir}/dinobase_{source_name}"
        if not Path(local_state_dir).exists():
            return

        cloud = CloudStorage(self.db.storage_url)
        state_url = f"{self.db.storage_url}_state/dinobase_{source_name}/"

        count = cloud.upload_dir(local_state_dir, state_url)
        if count > 0:
            print(f"  [state] saved pipeline state ({count} files)", file=sys.stderr)

    # ------------------------------------------------------------------
    # Parquet compaction
    # ------------------------------------------------------------------

    def _compact_source(self, source_name: str, result: SyncResult) -> None:
        """Compact parquet files for synced tables into single files."""
        if not self.db.is_cloud:
            return

        from dinobase.cloud import CloudStorage
        cloud = CloudStorage(self.db.storage_url)

        # Get all tables for this source from the DB
        tables = self.db.get_tables(source_name)

        for table_name in tables:
            if table_name.startswith("_dlt_") or table_name.startswith("_live_"):
                continue
            self._compact_table(cloud, source_name, table_name)

    def _compact_table(
        self, cloud: Any, source_name: str, table_name: str
    ) -> None:
        """Compact a single table's parquet files into one."""
        prefix = f"data/{source_name}/{table_name}/"
        files = cloud.list_files(self.db.storage_url + prefix, suffix=".parquet")

        if len(files) <= 1:
            return

        parquet_glob = f"{self.db.storage_url}{prefix}*.parquet"
        compacted_name = "_compacted.parquet"
        compacted_path = f"{self.db.storage_url}{prefix}{compacted_name}"

        try:
            self.db.conn.execute(
                f"COPY (SELECT * FROM read_parquet('{parquet_glob}')) "
                f"TO '{compacted_path}' (FORMAT PARQUET)"
            )
            deleted = cloud.delete_files(
                self.db.storage_url + prefix,
                exclude=[compacted_name],
            )
            print(
                f"  [compact] {source_name}.{table_name}: "
                f"{len(files)} files -> 1 (deleted {deleted})",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"  [compact] {source_name}.{table_name} failed: {e}", file=sys.stderr)

