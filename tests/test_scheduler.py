"""Tests for the sync scheduler."""

import os
import time
from datetime import datetime, timedelta

import pytest

from dinobase.db import DinobaseDB, META_SCHEMA
from dinobase.sync.scheduler import SyncScheduler, parse_interval


# --- parse_interval ---

def test_parse_seconds():
    assert parse_interval("60s") == 60
    assert parse_interval("1s") == 1


def test_parse_minutes():
    assert parse_interval("30m") == 1800
    assert parse_interval("5m") == 300


def test_parse_hours():
    assert parse_interval("1h") == 3600
    assert parse_interval("6h") == 21600


def test_parse_days():
    assert parse_interval("1d") == 86400


def test_parse_bare_number():
    assert parse_interval("3600") == 3600


# --- SyncScheduler ---

@pytest.fixture
def db(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    db = DinobaseDB(tmp_path / "test.duckdb")
    yield db
    db.close()


def test_source_needs_sync_never_synced(db):
    """Source that has never been synced should need sync."""
    scheduler = SyncScheduler(db, default_interval="1h")
    assert scheduler._source_needs_sync("stripe", {"type": "stripe"}) is True


def test_source_needs_sync_recently_synced(db):
    """Source synced recently should not need sync."""
    # Record a recent sync
    sync_id = db.log_sync_start("stripe", "stripe")
    db.log_sync_end(sync_id, "success", tables_synced=1, rows_synced=10)

    scheduler = SyncScheduler(db, default_interval="1h")
    assert scheduler._source_needs_sync("stripe", {"type": "stripe"}) is False


def test_source_needs_sync_stale(db):
    """Source synced long ago should need sync."""
    # Insert a sync record with an old timestamp
    db.conn.execute(
        f"INSERT INTO {META_SCHEMA}.sync_log "
        f"(connector_name, connector_type, started_at, finished_at, status) "
        f"VALUES ('stripe', 'stripe', "
        f"current_timestamp - INTERVAL '2 hours', "
        f"current_timestamp - INTERVAL '2 hours', 'success')"
    )

    scheduler = SyncScheduler(db, default_interval="1h")
    assert scheduler._source_needs_sync("stripe", {"type": "stripe"}) is True


def test_source_needs_sync_respects_per_source_interval(db):
    """Source with a custom interval should use that instead of the default."""
    sync_id = db.log_sync_start("stripe", "stripe")
    db.log_sync_end(sync_id, "success", tables_synced=1, rows_synced=10)

    scheduler = SyncScheduler(db, default_interval="1h")

    # With default 1h interval, recently synced = no sync needed
    assert scheduler._source_needs_sync("stripe", {"type": "stripe"}) is False

    # With a short interval and an old sync, needs sync.
    # Backdate the log so the source is older than 1s.
    db.conn.execute(
        "UPDATE _dinobase.sync_log SET finished_at = '2000-01-01' WHERE connector_name = 'stripe'"
    )
    assert scheduler._source_needs_sync(
        "stripe", {"type": "stripe", "sync_interval": "1s"}
    ) is True


def test_file_sources_never_need_sync(db):
    """Parquet and CSV sources should never be scheduled for sync."""
    scheduler = SyncScheduler(db, default_interval="1h")
    assert scheduler._source_needs_sync("demo", {"type": "parquet"}) is False
    assert scheduler._source_needs_sync("demo", {"type": "csv"}) is False


def test_background_start_stop(db):
    """Background thread should start and stop cleanly."""
    scheduler = SyncScheduler(db, default_interval="1h")
    scheduler.start_background(check_interval=1)

    assert scheduler._thread is not None
    assert scheduler._thread.is_alive()

    scheduler.stop()
    assert not scheduler._thread.is_alive() if scheduler._thread else True


def test_start_background_idempotent(db):
    """Starting background twice should not create a second thread."""
    scheduler = SyncScheduler(db, default_interval="1h")
    scheduler.start_background(check_interval=1)
    thread1 = scheduler._thread

    scheduler.start_background(check_interval=1)
    thread2 = scheduler._thread

    assert thread1 is thread2
    scheduler.stop()


def test_already_syncing_not_scheduled_again(db):
    """A source that's currently syncing should not be scheduled again."""
    scheduler = SyncScheduler(db, default_interval="1h")

    # Simulate that 'stripe' is currently syncing
    with scheduler._syncing_lock:
        scheduler._syncing.add("stripe")

    # Even though it's never been synced, it shouldn't be scheduled
    assert scheduler._source_needs_sync("stripe", {"type": "stripe"}) is False

    with scheduler._syncing_lock:
        scheduler._syncing.discard("stripe")


def test_max_workers_configurable(db):
    scheduler = SyncScheduler(db, default_interval="1h", max_workers=5)
    assert scheduler.max_workers == 5

    scheduler2 = SyncScheduler(db, default_interval="1h", max_workers=50)
    assert scheduler2.max_workers == 50
