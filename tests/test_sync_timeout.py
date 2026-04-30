"""Tests for the cooperative sync timeout via on_progress."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from dinobase.sync.engine import SyncEngine, SyncResult


def _make_engine():
    db = MagicMock()
    db.conn = MagicMock()
    db.is_cloud = False
    db.storage_url = None
    return SyncEngine(db)


def test_cooperative_timeout_fires():
    engine = _make_engine()

    def slow_pipeline(source_name, source_type, credentials, on_progress=None):
        # Simulate slow sync: call on_progress after sleeping past deadline
        time.sleep(0.3)
        if on_progress:
            on_progress(1, 5)
        return SyncResult(
            connector_name=source_name,
            connector_type=source_type,
            tables_synced=5,
            rows_synced=100,
            status="success",
        )

    with patch.object(engine, "_run_pipeline", side_effect=slow_pipeline):
        result = engine._run_pipeline_with_timeout(
            "test_source", "rest_api", {},
            timeout_seconds=0.1,
        )

    assert result.status == "error"
    assert "timed out" in result.error.lower()


def test_no_timeout_when_fast():
    engine = _make_engine()

    expected = SyncResult(
        connector_name="test_source",
        connector_type="rest_api",
        tables_synced=3,
        rows_synced=50,
        status="success",
    )

    def fast_pipeline(source_name, source_type, credentials, on_progress=None):
        if on_progress:
            on_progress(1, 3)
            on_progress(2, 3)
            on_progress(3, 3)
        return expected

    with patch.object(engine, "_run_pipeline", side_effect=fast_pipeline):
        result = engine._run_pipeline_with_timeout(
            "test_source", "rest_api", {},
            timeout_seconds=10,
        )

    assert result.status == "success"
    assert result.tables_synced == 3


def test_original_on_progress_called():
    engine = _make_engine()
    progress_calls = []

    def fast_pipeline(source_name, source_type, credentials, on_progress=None):
        if on_progress:
            on_progress(1, 2)
            on_progress(2, 2)
        return SyncResult(
            connector_name=source_name,
            connector_type=source_type,
            tables_synced=2,
            rows_synced=20,
            status="success",
        )

    def my_callback(synced, total):
        progress_calls.append((synced, total))

    with patch.object(engine, "_run_pipeline", side_effect=fast_pipeline):
        result = engine._run_pipeline_with_timeout(
            "test_source", "rest_api", {},
            on_progress=my_callback,
            timeout_seconds=10,
        )

    assert result.status == "success"
    assert progress_calls == [(1, 2), (2, 2)]
