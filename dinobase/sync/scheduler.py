"""Sync scheduler — runs syncs on configurable intervals per source.

Supports:
- Per-source intervals: e.g. billing syncs every 1h, CRM every 30m
- Global default interval
- Parallel sync for cloud mode (data goes to S3/GCS, no DuckDB contention)
- Sequential sync for local mode (dlt writes to DuckDB file; concurrent writes conflict)
- Foreground daemon mode (dinobase sync --schedule)
- Background thread mode (embedded in MCP server)
- Reliable: catches errors per-source, logs everything, never crashes
"""

from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from dinobase.config import get_connectors
from dinobase.db import DinobaseDB, META_SCHEMA
from dinobase.sync.engine import SyncEngine


DEFAULT_MAX_WORKERS_LOCAL = 1   # dlt writes to DuckDB file; concurrent writes conflict
DEFAULT_MAX_WORKERS_CLOUD = 8   # dlt writes parquet to object storage; safe to parallelize


def parse_interval(interval_str: str) -> int:
    """Parse an interval string like '1h', '30m', '6h', '1d' into seconds."""
    s = interval_str.strip().lower()
    if s.endswith("s"):
        result = int(s[:-1])
    elif s.endswith("m"):
        result = int(s[:-1]) * 60
    elif s.endswith("h"):
        result = int(s[:-1]) * 3600
    elif s.endswith("d"):
        result = int(s[:-1]) * 86400
    else:
        result = int(s)
    if result <= 0:
        raise ValueError(f"Sync interval must be positive, got: {interval_str!r}")
    return result


class SyncScheduler:
    """Manages scheduled syncs for all configured sources.

    Uses a thread pool so multiple sources sync concurrently.
    Each source gets its own dlt pipeline and writes independently.
    """

    def __init__(
        self,
        db: DinobaseDB,
        default_interval: str = "1h",
        max_workers: int | None = None,
    ):
        self.db = db
        self.default_interval_seconds = parse_interval(default_interval)
        if max_workers is None:
            max_workers = DEFAULT_MAX_WORKERS_CLOUD if db.is_cloud else DEFAULT_MAX_WORKERS_LOCAL
        self.max_workers = max_workers
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Track which sources are currently syncing to avoid overlap
        self._syncing: set[str] = set()
        self._syncing_lock = threading.Lock()

    def _get_last_sync_time(self, connector_name: str) -> datetime | None:
        """Get the last successful sync time for a connector."""
        result = self.db.conn.execute(
            f"SELECT MAX(finished_at) as last_sync FROM {META_SCHEMA}.sync_log "
            "WHERE connector_name = ? AND status = 'success'",
            [connector_name],
        )
        row = result.fetchone()
        if row and row[0]:
            return row[0]
        return None

    def _source_needs_sync(
        self, connector_name: str, source_config: dict[str, Any]
    ) -> bool:
        """Check if a connector is due for a sync based on its interval."""
        if source_config.get("type") in ("parquet", "csv"):
            return False

        # Don't schedule if already syncing
        with self._syncing_lock:
            if connector_name in self._syncing:
                return False

        interval_str = source_config.get("sync_interval", "")
        if not interval_str:
            interval_seconds = self.default_interval_seconds
        else:
            interval_seconds = parse_interval(interval_str)

        last_sync = self._get_last_sync_time(connector_name)
        if last_sync is None:
            return True

        elapsed = (datetime.now() - last_sync).total_seconds()
        return elapsed >= interval_seconds

    def _sync_one(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        """Sync a single source. Runs in a thread pool worker."""
        with self._syncing_lock:
            self._syncing.add(name)

        try:
            # Each thread gets its own SyncEngine with its own DB connection
            # to avoid DuckDB concurrent access issues
            engine = SyncEngine(DinobaseDB(self.db.db_path))

            _log(f"Syncing {name}...")
            result = engine.sync(name, config)

            if result.status == "success":
                _log(f"{name}: {result.tables_synced} tables, {result.rows_synced:,} rows")
            else:
                _log(f"{name}: ERROR — {result.error}")

            engine.db.close()

            return {
                "source": name,
                "status": result.status,
                "tables": result.tables_synced,
                "rows": result.rows_synced,
                "error": result.error,
            }
        except Exception as e:
            _log(f"{name}: UNEXPECTED ERROR — {e}")
            return {
                "source": name,
                "status": "error",
                "tables": 0,
                "rows": 0,
                "error": str(e),
            }
        finally:
            with self._syncing_lock:
                self._syncing.discard(name)

    def sync_all_due(self) -> list[dict[str, Any]]:
        """Sync all connectors that are due, concurrently via thread pool."""
        sources = get_connectors()

        due = {
            name: config
            for name, config in sources.items()
            if self._source_needs_sync(name, config)
        }

        if not due:
            return []

        _log(f"Starting sync for {len(due)} connector(s) (max {self.max_workers} concurrent)")

        results = []
        workers = min(self.max_workers, len(due))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._sync_one, name, config): name
                for name, config in due.items()
            }
            for future in as_completed(futures):
                results.append(future.result())

        succeeded = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "error")
        if results:
            _log(f"Sync complete: {succeeded} succeeded, {failed} failed")

        return results

    def run_loop(self, check_interval: int = 60) -> None:
        """Run the sync loop in the foreground."""
        _log(
            f"Scheduler started (checking every {check_interval}s, "
            f"default interval {self.default_interval_seconds}s, "
            f"max {self.max_workers} concurrent)"
        )

        sources = get_connectors()
        for name, config in sources.items():
            if config.get("type") in ("parquet", "csv"):
                continue
            interval = config.get("sync_interval", f"{self.default_interval_seconds}s")
            _log(f"  {name}: every {interval}")

        # Initial sync for anything that's due
        self.sync_all_due()

        while not self._stop_event.is_set():
            self._stop_event.wait(check_interval)
            if not self._stop_event.is_set():
                self.sync_all_due()

    def start_background(self, check_interval: int = 60) -> None:
        """Start the sync loop in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self.run_loop,
            args=(check_interval,),
            daemon=True,
            name="dinobase-sync-scheduler",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background sync loop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)
