"""Sync scheduler — runs syncs on configurable intervals per source.

Supports:
- Per-source intervals: e.g. billing syncs every 1h, CRM every 30m
- Global default interval
- Concurrent sync via thread pool (100 sources sync in parallel, not sequentially)
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

from dinobase.config import get_sources
from dinobase.db import DinobaseDB, META_SCHEMA
from dinobase.sync.engine import SyncEngine


DEFAULT_MAX_WORKERS = 10


def parse_interval(interval_str: str) -> int:
    """Parse an interval string like '1h', '30m', '6h', '1d' into seconds."""
    s = interval_str.strip().lower()
    if s.endswith("s"):
        return int(s[:-1])
    elif s.endswith("m"):
        return int(s[:-1]) * 60
    elif s.endswith("h"):
        return int(s[:-1]) * 3600
    elif s.endswith("d"):
        return int(s[:-1]) * 86400
    else:
        return int(s)


class SyncScheduler:
    """Manages scheduled syncs for all configured sources.

    Uses a thread pool so multiple sources sync concurrently.
    Each source gets its own dlt pipeline and writes independently.
    """

    def __init__(
        self,
        db: DinobaseDB,
        default_interval: str = "1h",
        max_workers: int = DEFAULT_MAX_WORKERS,
    ):
        self.db = db
        self.default_interval_seconds = parse_interval(default_interval)
        self.max_workers = max_workers
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Track which sources are currently syncing to avoid overlap
        self._syncing: set[str] = set()
        self._syncing_lock = threading.Lock()

    def _get_last_sync_time(self, source_name: str) -> datetime | None:
        """Get the last successful sync time for a source."""
        rows = self.db.query(
            f"SELECT MAX(finished_at) as last_sync FROM {META_SCHEMA}.sync_log "
            f"WHERE source_name = '{source_name}' AND status = 'success'"
        )
        if rows and rows[0]["last_sync"]:
            return rows[0]["last_sync"]
        return None

    def _source_needs_sync(
        self, source_name: str, source_config: dict[str, Any]
    ) -> bool:
        """Check if a source is due for a sync based on its interval."""
        if source_config.get("type") in ("parquet", "csv"):
            return False

        # Don't schedule if already syncing
        with self._syncing_lock:
            if source_name in self._syncing:
                return False

        interval_str = source_config.get("sync_interval", "")
        if not interval_str:
            interval_seconds = self.default_interval_seconds
        else:
            interval_seconds = parse_interval(interval_str)

        last_sync = self._get_last_sync_time(source_name)
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
        """Sync all sources that are due, concurrently via thread pool."""
        sources = get_sources()

        due = {
            name: config
            for name, config in sources.items()
            if self._source_needs_sync(name, config)
        }

        if not due:
            return []

        _log(f"Starting sync for {len(due)} source(s) (max {self.max_workers} concurrent)")

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

        sources = get_sources()
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
