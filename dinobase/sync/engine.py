"""Sync engine — wraps dlt to load data from sources into DuckDB."""

from __future__ import annotations

import json
import sys
import time
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import dlt

from dinobase.db import META_SCHEMA, DinobaseDB

# Workers for within-source resource parallelism.
# Local mode stays at 1: DuckDB file locking prevents concurrent writes.
# Cloud mode batches resources across 32 workers: each batch calls get_source()
# + pipeline.run() once for its slice, minimising SQLAlchemy/dlt overhead.
DEFAULT_PIPELINE_WORKERS_LOCAL = 1
DEFAULT_PIPELINE_WORKERS_CLOUD = 32


def _make_cloud_duckdb_conn(storage_url: str):
    """Create a fresh DuckDB in-memory connection configured for cloud storage.

    Used by parallel compaction workers so each thread has its own connection.
    Mirrors DinobaseDB._setup_httpfs / _setup_azure but operates on a new
    connection rather than self._conn.
    """
    import duckdb as _duckdb

    conn = _duckdb.connect(":memory:")
    storage_type = storage_url.split("://")[0] if "://" in storage_url else "s3"

    def _set(key: str, val: str) -> None:
        conn.execute(f"SET {key} = '{val.replace(chr(39), chr(39) * 2)}'")

    if storage_type == "azure":
        conn.execute("LOAD azure")
        if os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):
            _set("azure_storage_connection_string", os.environ["AZURE_STORAGE_CONNECTION_STRING"])
        else:
            if os.environ.get("AZURE_STORAGE_ACCOUNT_NAME"):
                _set("azure_account_name", os.environ["AZURE_STORAGE_ACCOUNT_NAME"])
            if os.environ.get("AZURE_STORAGE_ACCOUNT_KEY"):
                _set("azure_account_key", os.environ["AZURE_STORAGE_ACCOUNT_KEY"])
    else:
        conn.execute("LOAD httpfs")
        if storage_type in ("gs", "gcs"):
            conn.execute("SET s3_endpoint = 'storage.googleapis.com'")
            if os.environ.get("GCS_HMAC_KEY_ID"):
                _set("s3_access_key_id", os.environ["GCS_HMAC_KEY_ID"])
            if os.environ.get("GCS_HMAC_SECRET"):
                _set("s3_secret_access_key", os.environ["GCS_HMAC_SECRET"])
        else:
            if os.environ.get("AWS_ACCESS_KEY_ID"):
                _set("s3_access_key_id", os.environ["AWS_ACCESS_KEY_ID"])
            if os.environ.get("AWS_SECRET_ACCESS_KEY"):
                _set("s3_secret_access_key", os.environ["AWS_SECRET_ACCESS_KEY"])
            if os.environ.get("AWS_DEFAULT_REGION"):
                _set("s3_region", os.environ["AWS_DEFAULT_REGION"])
            elif os.environ.get("AWS_REGION"):
                _set("s3_region", os.environ["AWS_REGION"])
            if os.environ.get("S3_ENDPOINT"):
                _set("s3_endpoint", os.environ["S3_ENDPOINT"])
                conn.execute("SET s3_url_style = 'path'")

    return conn


def _is_int64_conflict(error_msg: str) -> bool:
    return (
        "INT128" in error_msg
        or ("out of range for the destination type" in error_msg and "INT64" in error_msg)
        or ("Could not convert" in error_msg and "INT64" in error_msg)
    )


def _is_unknown_identifier(error_msg: str) -> bool:
    return "UNKNOWN_IDENTIFIER" in error_msg or "Code: 47" in error_msg


@dataclass
class SyncResult:
    source_name: str
    source_type: str
    tables_synced: int
    rows_synced: int
    status: str
    error: str | None = None
    row_counts: dict[str, int] = field(default_factory=dict)
    table_names: list[str] = field(default_factory=list)


class SyncEngine:
    def __init__(self, db: DinobaseDB):
        self.db = db
        self._sync_t0: float | None = None
        self._log_fh = None

    # ------------------------------------------------------------------
    # Timing / logging
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        """Write a timestamped line to stderr and the active sync log file."""
        elapsed = time.monotonic() - self._sync_t0 if self._sync_t0 is not None else 0.0
        line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{elapsed:7.1f}s] {msg}"
        print(line, file=sys.stderr)
        if self._log_fh is not None:
            self._log_fh.write(line + "\n")
            self._log_fh.flush()

    def sync(
        self,
        source_name: str,
        source_config: dict[str, Any],
        on_progress: "Callable[[int, int], None] | None" = None,
    ) -> SyncResult:
        """Sync a single source into DuckDB."""
        source_type = source_config["type"]
        credentials = source_config.get("credentials", {})

        # Local connectors use a lightweight fetch path (no dlt pipeline)
        from dinobase.fetch.connector import is_local_connector

        if is_local_connector(source_name) or is_local_connector(source_type):
            return self._sync_local_connector(source_name, source_config)

        # Open log file and start timing
        self._sync_t0 = time.monotonic()
        log_dir = os.environ.get("DINOBASE_SYNC_LOG_DIR", "/tmp")
        log_path = os.path.join(
            log_dir,
            f"dinobase_sync_{source_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        )
        try:
            self._log_fh = open(log_path, "w")  # noqa: WPS515
        except OSError:
            self._log_fh = None
        self._log(f"=== SYNC START: {source_name} ({source_type}) ===")
        self._log(f"log: {log_path}")

        # Refresh OAuth tokens if expired
        from dinobase.auth import ensure_fresh_credentials
        credentials = ensure_fresh_credentials(source_name, source_type, credentials)
        self._log("ensure_fresh_credentials done")

        cloud = None
        sync_id = None

        try:
            # Distributed lock for cloud mode — acquired inside try so finally
            # always releases it, even if an exception fires before we enter
            # the pipeline (e.g. a DB sequence conflict on log_sync_start).
            if self.db.is_cloud:
                from dinobase.cloud import CloudStorage
                cloud = CloudStorage(self.db.storage_url)
                if not cloud.acquire_lock(source_name):
                    self._log("lock not acquired — another process is syncing")
                    return SyncResult(
                        source_name=source_name,
                        source_type=source_type,
                        tables_synced=0,
                        rows_synced=0,
                        status="skipped",
                        error="Another process is syncing this source",
                    )
                self._log("lock acquired")

            sync_id = self.db.log_sync_start(source_name, source_type)
            self._log("log_sync_start done")

            self._log("_run_pipeline START")
            result = self._run_pipeline(source_name, source_type, credentials, on_progress=on_progress)
            self._log(
                f"_run_pipeline DONE: {result.tables_synced} tables, "
                f"{result.rows_synced:,} rows"
            )

            # Use table names from the sync result (avoids querying information_schema
            # which requires views to exist — views are now created lazily on demand).
            if result.table_names:
                synced_tables = result.table_names
            else:
                synced_tables = [
                    t for t in self.db.get_tables(source_name)
                    if not t.startswith("_dlt_")
                ]
            self._log(f"get_tables done: {len(synced_tables)} tables")

            self._log("extract_metadata START")
            from dinobase.sync.sources import extract_metadata
            annotations = extract_metadata(source_type, credentials, synced_tables)
            annotated = sum(len(v) for v in annotations.values())
            self._log(f"extract_metadata DONE: {annotated} annotated columns")

            self._log("update_table_metadata START")
            self.db.update_table_metadata(
                source_name, source_name, annotations=annotations,
                row_counts=result.row_counts if self.db.is_cloud else None,
                override_tables=synced_tables if self.db.is_cloud else None,
            )
            self._log("update_table_metadata DONE")

            # Clear live data — parquet is now fresh.
            # 1. _dinobase.live_rows metadata table
            # 2. In-memory _live_* staging tables (mutation writes accumulate here
            #    between syncs; after sync the parquet reflects them, so clear staging
            #    to avoid stale rows shadowing freshly synced parquet data)
            self._log("clear_live_rows START")
            self.db.clear_live_rows(source_name)
            if self.db.is_cloud:
                for t in synced_tables:
                    staging = f"_live_{t}"
                    try:
                        self.db.conn.execute(f'DELETE FROM "{source_name}"."{staging}"')
                    except Exception:
                        pass
            self._log("clear_live_rows DONE")

            self.db.log_sync_end(
                sync_id,
                status="success",
                tables_synced=result.tables_synced,
                rows_synced=result.rows_synced,
            )
            self._log("log_sync_end done")

            from dinobase import telemetry
            telemetry.capture("sync_completed", {
                "source_name": source_name,
                "source_type": source_type,
                "tables_synced": result.tables_synced,
                "rows_synced": result.rows_synced,
                "duration_seconds": round(time.monotonic() - self._sync_t0, 2),
                "storage_mode": "cloud" if self.db.is_cloud else "local",
            })
            from dinobase.semantic_agent import spawn_semantic_agent
            spawn_semantic_agent(source_name)
            self._log(f"=== SYNC COMPLETE: total {time.monotonic() - self._sync_t0:.1f}s ===")
            return result
        except Exception as e:
            error_msg = str(e)
            self._log(f"=== SYNC ERROR: {type(e).__name__}: {error_msg} ===")
            if sync_id is not None:
                self.db.log_sync_end(sync_id, status="error", error_message=error_msg)
            from dinobase import telemetry
            telemetry.capture("sync_failed", {
                "source_name": source_name,
                "source_type": source_type,
                "duration_seconds": round(time.monotonic() - self._sync_t0, 2),
                "storage_mode": "cloud" if self.db.is_cloud else "local",
                "error_type": type(e).__name__,
            })
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
            if self._log_fh is not None:
                self._log_fh.close()
                self._log_fh = None
            self._sync_t0 = None

    def _sync_local_connector(
        self,
        source_name: str,
        source_config: dict[str, Any],
    ) -> SyncResult:
        """Lightweight sync for local connectors — uses dlt iteration + JSON cache."""
        from dinobase.fetch.connector import LocalConnectorFetcher

        source_type = source_config["type"]
        t0 = time.monotonic()

        try:
            fetcher = LocalConnectorFetcher(self.db, source_name)
            paths = fetcher.fetch_all()

            total_rows = 0
            for cache_path in paths.values():
                with open(cache_path) as f:
                    total_rows += len(json.loads(f.read()))

            elapsed = time.monotonic() - t0
            print(
                f"  Synced {len(paths)} table(s), {total_rows:,} rows "
                f"in {elapsed:.1f}s (local connector)",
                file=sys.stderr,
            )

            sync_id = self.db.log_sync_start(source_name, source_type)
            self.db.log_sync_end(
                sync_id,
                status="success",
                tables_synced=len(paths),
                rows_synced=total_rows,
            )

            return SyncResult(
                source_name=source_name,
                source_type=source_type,
                tables_synced=len(paths),
                rows_synced=total_rows,
                status="success",
                table_names=list(paths.keys()),
            )
        except Exception as e:
            return SyncResult(
                source_name=source_name,
                source_type=source_type,
                tables_synced=0,
                rows_synced=0,
                status="error",
                error=str(e),
            )

    def _run_pipeline(
        self,
        source_name: str,
        source_type: str,
        credentials: dict[str, str],
        resource_names: list[str] | None = None,
        on_progress: "Callable[[int, int], None] | None" = None,
        max_workers: int | None = None,
    ) -> SyncResult:
        from dinobase.sync.sources import get_source

        # Resolve worker count: explicit arg > cloud/local default
        _workers = max_workers if max_workers is not None else (
            DEFAULT_PIPELINE_WORKERS_CLOUD if self.db.is_cloud else DEFAULT_PIPELINE_WORKERS_LOCAL
        )

        # Choose destination and pipelines_dir based on storage mode
        if self.db.is_cloud:
            import tempfile
            pipelines_dir = tempfile.mkdtemp(prefix="dinobase_")
            destination = dlt.destinations.filesystem(
                bucket_url=self.db.storage_url + "data/",
                layout="{schema_name}/{table_name}/{load_id}.{file_id}.{ext}",
            )
        else:
            destination = dlt.destinations.duckdb(self.db.db_path)
            import os as _os
            pipelines_dir = _os.path.join(_os.path.dirname(self.db.db_path), "_pipelines")
            _os.makedirs(pipelines_dir, exist_ok=True)

        # Discover all resources first so we can report per-table progress.
        self._log("probe get_source START")
        probe_source = get_source(source_type, credentials, resource_names=resource_names)
        all_resource_names: list[str] = [
            name for name, res in probe_source.resources.items() if res.selected
        ]
        total_resources = len(all_resource_names)
        _mode = f"parallel/{_workers} workers" if _workers > 1 else "sequential"
        self._log(
            f"probe get_source DONE: {total_resources} resources [{_mode}]"
        )

        # Announce total immediately so the frontend can display a progress bar
        # even before the first table finishes.
        if on_progress:
            on_progress(0, total_resources)

        # Dispatch to sequential or parallel path
        self._log(f"pipeline dispatch START")
        if _workers <= 1:
            _first_load_info, _tables_done = self._run_resources_sequential(
                source_name, source_type, credentials, destination, pipelines_dir,
                all_resource_names, on_progress,
            )
        else:
            _first_load_info, _tables_done = self._run_resources_parallel(
                source_name, source_type, credentials, destination, pipelines_dir,
                all_resource_names, on_progress, _workers,
            )
        self._log(f"pipeline dispatch DONE: {_tables_done}/{total_resources} tables loaded")

        if self.db.is_cloud:
            if _first_load_info is not None:
                self._log("register_cloud_source START")
                result = self._register_cloud_source(source_name, source_type, _first_load_info)
                self._log(
                    f"register_cloud_source DONE: {result.tables_synced} tables, "
                    f"{result.rows_synced:,} rows"
                )
                self._log("compact_source START")
                self._compact_source(source_name, result)
                self._log("compact_source DONE")
                return result

            return SyncResult(
                source_name=source_name,
                source_type=source_type,
                tables_synced=0,
                rows_synced=0,
                status="success",
            )

        # Count tables and rows from DuckDB (local mode)
        tables_synced = 0
        rows_synced = 0
        if _first_load_info is not None:
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

    # ------------------------------------------------------------------
    # Resource execution helpers
    # ------------------------------------------------------------------

    def _run_resources_sequential(
        self,
        source_name: str,
        source_type: str,
        credentials: dict[str, str],
        destination: Any,
        pipelines_dir: str,
        all_resource_names: list[str],
        on_progress: "Callable[[int, int], None] | None",
    ) -> "tuple[Any, int]":
        """Run resources one at a time, each with its own isolated pipeline."""
        from dinobase.sync.sources import get_source

        _first_load_info = None
        _tables_done = 0

        for _resource_name in all_resource_names:
            _pipeline_name = f"dinobase_{source_name}__{_resource_name}"
            if self.db.is_cloud:
                self._restore_state(_pipeline_name, pipelines_dir)
            pipeline = dlt.pipeline(
                pipeline_name=_pipeline_name,
                destination=destination,
                dataset_name=source_name,
                progress="log",
                pipelines_dir=pipelines_dir,
            )
            _skipped = False
            _last_emsg = ""
            try:
                for _attempt in range(5):
                    try:
                        _resource_source = get_source(
                            source_type, credentials, resource_names=[_resource_name]
                        )
                        _load_info = pipeline.run(_resource_source, loader_file_format="parquet")
                        if _load_info.loads_ids and _first_load_info is None:
                            _first_load_info = _load_info
                        break
                    except Exception as _e:
                        _last_emsg = str(_e)
                        if _is_int64_conflict(_last_emsg):
                            print(
                                f"  [schema-reset] INT64 conflict on '{_resource_name}' "
                                f"— dropping stale schema and retrying.",
                                file=sys.stderr,
                            )
                            if not self.db.is_cloud:
                                try:
                                    self.db.conn.execute(
                                        f'DROP SCHEMA IF EXISTS "{source_name}" CASCADE'
                                    )
                                except Exception as _drop_err:
                                    print(f"  [schema-reset] DROP SCHEMA failed: {_drop_err}", file=sys.stderr)
                            pipeline.drop()
                        elif _is_unknown_identifier(_last_emsg) and source_type == "clickhouse":
                            print(
                                f"  [ephemeral-skip] ClickHouse UNKNOWN_IDENTIFIER on "
                                f"'{_resource_name}' — skipping.",
                                file=sys.stderr,
                            )
                            _skipped = True
                            break
                        else:
                            raise
                else:
                    raise RuntimeError(
                        f"Sync of {source_name}.{_resource_name} failed after "
                        f"5 attempts. Last error: {_last_emsg}"
                    )
            finally:
                if self.db.is_cloud:
                    self._save_state(_pipeline_name, pipelines_dir)

            if not _skipped:
                _tables_done += 1
            if on_progress:
                on_progress(_tables_done, len(all_resource_names))

        return _first_load_info, _tables_done

    def _run_resources_parallel(
        self,
        source_name: str,
        source_type: str,
        credentials: dict[str, str],
        destination: Any,
        pipelines_dir: str,
        all_resource_names: list[str],
        on_progress: "Callable[[int, int], None] | None",
        max_workers: int,
    ) -> "tuple[Any, int]":
        """Run resources in parallel using batched pipelines.

        Resources are sorted and distributed round-robin into `max_workers` batches.
        Each batch worker calls get_source() + pipeline.run() ONCE for its entire
        slice, dramatically reducing SQLAlchemy engine creations and dlt overhead.

        Pipeline names: dinobase_{source_name}__b{idx:04d} (deterministic, stable).
        If a batch fails, it falls back to per-resource execution so one bad table
        doesn't block the rest.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        from dinobase.sync.sources import get_source

        _first_load_info: Any = None
        _first_load_info_lock = threading.Lock()
        _tables_done = 0
        _tables_done_lock = threading.Lock()
        # Set when any exception exits the as_completed loop; workers check
        # this before starting to avoid unnecessary work after cancellation.
        _cancel_event = threading.Event()

        # Distribute resources deterministically across batches (round-robin, sorted)
        sorted_resources = sorted(all_resource_names)
        n_batches = min(max_workers, len(sorted_resources))
        batches: list[list[str]] = [[] for _ in range(n_batches)]
        for i, name in enumerate(sorted_resources):
            batches[i % n_batches].append(name)

        def _sync_batch(batch_idx: int, batch_resources: list[str]) -> "tuple[Any, int]":
            if _cancel_event.is_set():
                return None, 0

            pipeline_name = f"dinobase_{source_name}__b{batch_idx:04d}"
            if self.db.is_cloud:
                self._restore_state(pipeline_name, pipelines_dir)
            pipeline = dlt.pipeline(
                pipeline_name=pipeline_name,
                destination=destination,
                dataset_name=source_name,
                progress="log",
                pipelines_dir=pipelines_dir,
            )
            tables_done = 0
            _load_info = None
            try:
                src = get_source(source_type, credentials, resource_names=batch_resources)
                _load_info = pipeline.run(src, loader_file_format="parquet")
                tables_done = len(batch_resources)
            except Exception as batch_err:
                # One bad resource poisoned the batch — fall back to per-resource
                print(
                    f"  [batch-{batch_idx}] failed ({batch_err!r}), falling back to per-resource",
                    file=sys.stderr,
                )
                for resource_name in batch_resources:
                    if _cancel_event.is_set():
                        break
                    resource_pipeline_name = f"dinobase_{source_name}__{resource_name}"
                    if self.db.is_cloud:
                        self._restore_state(resource_pipeline_name, pipelines_dir)
                    res_pipeline = dlt.pipeline(
                        pipeline_name=resource_pipeline_name,
                        destination=destination,
                        dataset_name=source_name,
                        progress="log",
                        pipelines_dir=pipelines_dir,
                    )
                    try:
                        for _attempt in range(5):
                            try:
                                res_src = get_source(
                                    source_type, credentials, resource_names=[resource_name]
                                )
                                res_load = res_pipeline.run(res_src, loader_file_format="parquet")
                                if res_load.loads_ids and _load_info is None:
                                    _load_info = res_load
                                tables_done += 1
                                break
                            except Exception as _e:
                                _emsg = str(_e)
                                if _is_int64_conflict(_emsg):
                                    print(
                                        f"  [schema-reset] INT64 conflict on '{resource_name}' "
                                        f"— dropping stale schema and retrying.",
                                        file=sys.stderr,
                                    )
                                    res_pipeline.drop()
                                elif _is_unknown_identifier(_emsg) and source_type == "clickhouse":
                                    print(
                                        f"  [ephemeral-skip] ClickHouse UNKNOWN_IDENTIFIER on "
                                        f"'{resource_name}' — skipping.",
                                        file=sys.stderr,
                                    )
                                    break
                                else:
                                    raise
                        else:
                            raise RuntimeError(
                                f"Sync of {source_name}.{resource_name} failed after 5 attempts"
                            )
                    finally:
                        if self.db.is_cloud:
                            self._save_state(resource_pipeline_name, pipelines_dir)
            finally:
                if self.db.is_cloud:
                    self._save_state(pipeline_name, pipelines_dir)

            return _load_info, tables_done

        pool = ThreadPoolExecutor(max_workers=n_batches)
        futures = {
            pool.submit(_sync_batch, idx, batch): idx
            for idx, batch in enumerate(batches)
        }
        try:
            for future in as_completed(futures):
                load_info, done_count = future.result()
                if done_count:
                    with _tables_done_lock:
                        _tables_done += done_count
                with _first_load_info_lock:
                    if load_info is not None and load_info.loads_ids and _first_load_info is None:
                        _first_load_info = load_info
                if on_progress:
                    on_progress(_tables_done, len(all_resource_names))
                    # _SyncCancelled raised here exits this loop; _cancel_event
                    # prevents pending batches from starting unnecessary work.
        except BaseException:
            _cancel_event.set()
            raise
        finally:
            # cancel_futures=True skips queued-but-not-started tasks (Python 3.9+)
            pool.shutdown(wait=True, cancel_futures=True)

        return _first_load_info, _tables_done

    # ------------------------------------------------------------------
    # Pipeline state persistence (incremental sync support)
    # ------------------------------------------------------------------

    def _restore_state(self, pipeline_name: str, pipelines_dir: str) -> None:
        """Download dlt pipeline state from cloud storage."""
        from dinobase.cloud import CloudStorage

        cloud = CloudStorage(self.db.storage_url)
        count = cloud.download_dir(
            f"{self.db.storage_url}_state/{pipeline_name}/",
            f"{pipelines_dir}/{pipeline_name}",
        )
        if count > 0:
            print(f"  [state] restored {pipeline_name} ({count} files)", file=sys.stderr)

    def _save_state(self, pipeline_name: str, pipelines_dir: str) -> None:
        """Upload dlt pipeline state to cloud storage."""
        from pathlib import Path
        from dinobase.cloud import CloudStorage

        local = f"{pipelines_dir}/{pipeline_name}"
        if not Path(local).exists():
            return

        cloud = CloudStorage(self.db.storage_url)
        count = cloud.upload_dir(local, f"{self.db.storage_url}_state/{pipeline_name}/")
        if count > 0:
            print(f"  [state] saved {pipeline_name} ({count} files)", file=sys.stderr)

    # ------------------------------------------------------------------
    # Cloud source registration
    # ------------------------------------------------------------------

    def _register_cloud_source(
        self, source_name: str, source_type: str, load_info: Any,
    ) -> SyncResult:
        """After cloud sync, create DuckDB views over the written parquet files."""
        table_parquet_globs = self.db._discover_table_parquet_paths(source_name)
        # Persist paths so future server startups skip S3 directory scanning
        if table_parquet_globs:
            self.db.save_parquet_paths(source_name, table_parquet_globs)

        self.db.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{source_name}"')

        # ------------------------------------------------------------------
        # Pre-fetch row counts in ONE bulk call using all per-table globs.
        # parquet_file_metadata() returns file_name + num_rows per file.
        # We pass a Python list of globs so DuckDB expands them in one shot.
        # ------------------------------------------------------------------
        per_table_row_counts: dict[str, int] = {}
        try:
            glob_list = list(table_parquet_globs.values())
            rows = self.db.conn.execute(
                "SELECT regexp_extract(file_name, '.*/([^/]+)/[^/]+$', 1) AS tbl, "
                "SUM(num_rows) AS cnt "
                "FROM parquet_file_metadata($globs) "
                "GROUP BY 1",
                {"globs": glob_list},
            ).fetchall()
            for tbl, cnt in rows:
                if tbl and not tbl.startswith("_"):
                    per_table_row_counts[tbl] = int(cnt or 0)
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Pre-fetch stored column schemas from _dinobase.columns so we can
        # recreate staging tables without reading S3 parquet files.
        # On first sync these are empty; we fall back to the slow S3 path for
        # those tables. On every subsequent sync (even after server restart)
        # the schemas come from this in-memory lookup.
        # ------------------------------------------------------------------
        stored_schemas = self.db.get_stored_column_schemas(source_name, source_name)

        self.db.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{source_name}"')

        table_names: list[str] = []
        tables_synced = 0
        rows_synced = 0

        for table_name, parquet_glob in table_parquet_globs.items():
            staging_table = f"_live_{table_name}"
            try:
                # Staging table: fast path uses stored column schema (no S3).
                # Slow path (first sync, no stored schema): reads schema from parquet.
                if stored_schemas.get(table_name):
                    col_defs = ", ".join(
                        f'"{col}" {dtype}'
                        for col, dtype in stored_schemas[table_name]
                    )
                    self.db.conn.execute(
                        f'CREATE TABLE IF NOT EXISTS "{source_name}"."{staging_table}" '
                        f"({col_defs})"
                    )
                else:
                    self.db.conn.execute(
                        f'CREATE TABLE IF NOT EXISTS "{source_name}"."{staging_table}" '
                        f"AS SELECT * FROM read_parquet('{parquet_glob}') WHERE false"
                    )
                # UNION ALL view (staging + parquet).
                # IF NOT EXISTS: when the server stays running between syncs these
                # are already in memory — skips all S3 reads for view creation.
                # First sync after restart: must create views. Using explicit column
                # names (from stored schema) halves the cost vs SELECT * by needing
                # only one parquet schema read per view instead of two.
                cols = stored_schemas.get(table_name)
                if cols:
                    col_list = ", ".join(f'"{col}"' for col, _ in cols)
                    has_id = any(col == "id" for col, _ in cols)
                    if has_id:
                        view_sql = (
                            f'CREATE VIEW IF NOT EXISTS "{source_name}"."{table_name}" AS '
                            f'SELECT {col_list} FROM "{source_name}"."{staging_table}" '
                            f"UNION ALL "
                            f"SELECT {col_list} FROM read_parquet('{parquet_glob}') "
                            f"WHERE CAST(id AS VARCHAR) NOT IN ("
                            f'  SELECT CAST(id AS VARCHAR) FROM "{source_name}"."{staging_table}"'
                            f")"
                        )
                    else:
                        view_sql = (
                            f'CREATE VIEW IF NOT EXISTS "{source_name}"."{table_name}" AS '
                            f'SELECT {col_list} FROM read_parquet(\'{parquet_glob}\') '
                            f'UNION ALL SELECT {col_list} FROM "{source_name}"."{staging_table}"'
                        )
                    self.db.conn.execute(view_sql)
                else:
                    # First sync — no stored schema, fall back to SELECT *
                    dedup_sql = (
                        f'CREATE VIEW IF NOT EXISTS "{source_name}"."{table_name}" AS '
                        f'SELECT * FROM "{source_name}"."{staging_table}" '
                        f"UNION ALL "
                        f"SELECT * FROM read_parquet('{parquet_glob}') "
                        f"WHERE CAST(id AS VARCHAR) NOT IN ("
                        f'  SELECT CAST(id AS VARCHAR) FROM "{source_name}"."{staging_table}"'
                        f")"
                    )
                    simple_sql = (
                        f'CREATE VIEW IF NOT EXISTS "{source_name}"."{table_name}" AS '
                        f"SELECT * FROM read_parquet('{parquet_glob}') "
                        f'UNION ALL SELECT * FROM "{source_name}"."{staging_table}"'
                    )
                    try:
                        self.db.conn.execute(dedup_sql)
                    except Exception:
                        self.db.conn.execute(simple_sql)

                row_count = per_table_row_counts.get(table_name)
                if row_count is None:
                    try:
                        res = self.db.conn.execute(
                            f"SELECT COALESCE(SUM(num_rows), 0) "
                            f"FROM parquet_file_metadata('{parquet_glob}')"
                        ).fetchone()
                        row_count = int(res[0]) if res else 0
                    except Exception:
                        row_count = 0
                    per_table_row_counts[table_name] = row_count
                table_names.append(table_name)
                tables_synced += 1
                rows_synced += row_count
            except Exception as e:
                if "No files found" not in str(e):
                    print(f"  [cloud] failed to register {source_name}.{table_name}: {e}", file=sys.stderr)

        return SyncResult(
            source_name=source_name,
            source_type=source_type,
            tables_synced=tables_synced,
            rows_synced=rows_synced,
            status="success",
            row_counts=per_table_row_counts,
            table_names=table_names,
        )

    # ------------------------------------------------------------------
    # Parquet compaction
    # ------------------------------------------------------------------

    def _compact_source(self, source_name: str, result: SyncResult) -> None:
        """Compact parquet files for synced tables into single files.

        Uses one S3 glob to find all files (instead of one LIST per table),
        and batch-deletes old files after compaction.
        """
        if not self.db.is_cloud:
            return

        from dinobase.cloud import CloudStorage
        cloud = CloudStorage(self.db.storage_url)

        # Step 1: Get all parquet files under this source in ONE S3 call.
        # This replaces the previous per-table cloud.list_files() loop.
        source_fs_prefix = cloud._to_fs_path(
            f"{self.db.storage_url}data/{source_name}/"
        )
        self._log("compact: glob all parquet files...")
        try:
            all_files: set[str] = set(
                cloud.fs.glob(source_fs_prefix + "**/*.parquet")
            )
        except Exception:
            return

        self._log(f"compact: glob done — {len(all_files)} files found")
        if not all_files:
            return

        # Step 2: Get the table → S3 prefix mapping (2 LIST calls via _discover).
        table_parquet_globs = self.db._discover_table_parquet_paths(source_name)
        self._log(f"compact: discover table paths done — {len(table_parquet_globs)} tables")

        # Step 3: Identify tables that need compaction.
        to_compact: list[tuple[str, str, list[str]]] = []
        for table_name, glob_url in table_parquet_globs.items():
            if table_name.startswith("_dlt_") or table_name.startswith("_live_"):
                continue
            table_url_prefix = glob_url.rsplit("/", 1)[0] + "/"
            table_fs_prefix = cloud._to_fs_path(table_url_prefix)
            table_files = [f for f in all_files if f.startswith(table_fs_prefix)]
            if len(table_files) > 1:
                to_compact.append((table_name, table_url_prefix, table_files))

        if not to_compact:
            self._log("compact: nothing to compact")
            return

        # Step 4: Compact in parallel — each worker uses its own DuckDB connection
        # so they don't block on a single shared connection.
        from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

        storage_url = self.db.storage_url

        def _compact_worker(
            table_name: str, table_url_prefix: str, table_files: list[str]
        ) -> tuple[str, int, str | None]:
            parquet_glob = table_url_prefix + "*.parquet"
            compacted_path = table_url_prefix + "_compacted.parquet"
            conn = _make_cloud_duckdb_conn(storage_url)
            err = None
            try:
                conn.execute(
                    f"COPY (SELECT * FROM read_parquet('{parquet_glob}')) "
                    f"TO '{compacted_path}' (FORMAT PARQUET)"
                )
                to_delete = [f for f in table_files if not f.endswith("/_compacted.parquet")]
                if to_delete:
                    from dinobase.cloud import CloudStorage as _CS
                    try:
                        _CS(storage_url).fs.rm(to_delete)
                    except Exception:
                        for _f in to_delete:
                            try:
                                _CS(storage_url).fs.rm(_f)
                            except Exception:
                                pass
            except Exception as _e:
                err = str(_e)
            finally:
                conn.close()
            return table_name, len(table_files), err

        _t_par = time.monotonic()
        with ThreadPoolExecutor(max_workers=min(8, len(to_compact))) as pool:
            futures = {
                pool.submit(_compact_worker, tn, tu, tf): tn
                for tn, tu, tf in to_compact
            }
            compacted = 0
            for future in _as_completed(futures):
                tn, n_files, err = future.result()
                if err:
                    self._log(f"compact: {tn} failed: {err}")
                else:
                    self._log(f"compact: {tn} {n_files} files→1")
                    compacted += 1

        self._log(
            f"compact: {compacted}/{len(to_compact)} tables done "
            f"({time.monotonic() - _t_par:.1f}s parallel)"
        )

