"""Tests for freshness detection, staleness thresholds, and the refresh workflow."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import pytest

from dinobase.config import (
    _parse_duration,
    _source_category,
    get_freshness_threshold,
)
from dinobase.query.engine import QueryEngine, _human_duration


# ---------------------------------------------------------------------------
# Unit tests: duration parsing
# ---------------------------------------------------------------------------

def test_parse_duration_hours():
    assert _parse_duration("1h") == 3600
    assert _parse_duration("6h") == 21600


def test_parse_duration_minutes():
    assert _parse_duration("30m") == 1800


def test_parse_duration_days():
    assert _parse_duration("1d") == 86400


def test_parse_duration_seconds():
    assert _parse_duration("120s") == 120


def test_parse_duration_raw_int():
    assert _parse_duration("3600") == 3600


# ---------------------------------------------------------------------------
# Unit tests: human duration formatting
# ---------------------------------------------------------------------------

def test_human_duration_seconds():
    assert _human_duration(45) == "45s"


def test_human_duration_minutes():
    assert _human_duration(300) == "5m"


def test_human_duration_hours():
    assert _human_duration(3600) == "1h"


def test_human_duration_hours_minutes():
    assert _human_duration(5400) == "1h 30m"


# ---------------------------------------------------------------------------
# Unit tests: source category detection
# ---------------------------------------------------------------------------

def test_source_category_file():
    assert _source_category("parquet") == "file"
    assert _source_category("csv") == "file"


def test_source_category_saas():
    assert _source_category("stripe") == "saas"
    assert _source_category("hubspot") == "saas"


# ---------------------------------------------------------------------------
# Integration tests: freshness threshold from config
# ---------------------------------------------------------------------------

def test_freshness_threshold_default_saas(tmp_path):
    """SaaS sources default to 1h."""
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    from dinobase.config import save_config
    save_config({
        "sources": {
            "stripe": {"type": "stripe", "credentials": {"api_key": "sk_test"}}
        }
    })
    threshold = get_freshness_threshold("stripe")
    assert threshold == 3600  # 1h


def test_freshness_threshold_explicit(tmp_path):
    """Explicit threshold overrides default."""
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    from dinobase.config import save_config
    save_config({
        "sources": {
            "stripe": {
                "type": "stripe",
                "credentials": {"api_key": "sk_test"},
                "freshness_threshold": "30m",
            }
        }
    })
    threshold = get_freshness_threshold("stripe")
    assert threshold == 1800  # 30m


def test_freshness_threshold_file_source(tmp_path):
    """File sources should return None (never stale)."""
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    from dinobase.config import save_config
    save_config({
        "sources": {
            "events": {"type": "parquet", "credentials": {"path": "/data"}}
        }
    })
    threshold = get_freshness_threshold("events")
    assert threshold is None


# ---------------------------------------------------------------------------
# Integration tests: get_freshness on QueryEngine
# ---------------------------------------------------------------------------

def test_get_freshness_fresh_source(sample_db):
    """Source synced moments ago should be fresh."""
    engine = QueryEngine(sample_db)
    freshness = engine.get_freshness("stripe")

    assert freshness["last_sync"] is not None
    assert freshness["is_stale"] is False
    assert freshness["threshold"] is not None


def test_get_freshness_stale_source(sample_db):
    """Source synced long ago should be stale."""
    # Backdate the sync log to 3 hours ago.
    # get_freshness() treats stored naive datetimes as UTC (via replace(tzinfo=utc)),
    # so we must store a naive UTC timestamp to get the correct age.
    old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
    sample_db.conn.execute(
        "UPDATE _dinobase.sync_log SET finished_at = ? WHERE connector_name = 'stripe'",
        [old_time],
    )

    engine = QueryEngine(sample_db)
    freshness = engine.get_freshness("stripe")

    assert freshness["is_stale"] is True
    assert freshness["age_seconds"] > 3600  # > 1h
    assert freshness["age_human"] is not None


def test_get_freshness_never_synced(sample_db):
    """Source with no sync log should be stale."""
    # Create a schema with no sync log entries
    sample_db.conn.execute("CREATE SCHEMA new_source")
    sample_db.conn.execute("CREATE TABLE new_source.data (id INT)")

    engine = QueryEngine(sample_db)
    freshness = engine.get_freshness("new_source")

    assert freshness["last_sync"] is None
    assert freshness["is_stale"] is True


# ---------------------------------------------------------------------------
# Integration tests: list_connectors includes freshness
# ---------------------------------------------------------------------------

def test_list_connectors_includes_freshness(sample_db):
    """list_connectors should include freshness fields."""
    engine = QueryEngine(sample_db)
    result = engine.list_connectors()

    stripe = next(s for s in result["connectors"] if s["name"] == "stripe")
    assert "last_sync" in stripe
    assert "is_stale" in stripe
    assert "age" in stripe
    assert "freshness_threshold" in stripe


def test_list_connectors_stale_flag(sample_db):
    """Stale connectors should have is_stale=True in list_connectors."""
    old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
    sample_db.conn.execute(
        "UPDATE _dinobase.sync_log SET finished_at = ? WHERE connector_name = 'stripe'",
        [old_time],
    )

    engine = QueryEngine(sample_db)
    result = engine.list_connectors()

    stripe = next(s for s in result["connectors"] if s["name"] == "stripe")
    assert stripe["is_stale"] is True


# ---------------------------------------------------------------------------
# Integration tests: describe_table includes freshness
# ---------------------------------------------------------------------------

def test_describe_includes_freshness(sample_db):
    """describe_table should include last_sync and staleness."""
    engine = QueryEngine(sample_db)
    result = engine.describe_table("stripe.customers")

    assert "last_sync" in result
    assert "is_stale" in result
