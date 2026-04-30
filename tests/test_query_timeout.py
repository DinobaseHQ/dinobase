"""Tests for query timeout and memory limit parameters."""

from __future__ import annotations

import os

import pytest

from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine


@pytest.fixture
def db(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    _db = DinobaseDB(tmp_path / "test.duckdb")
    _db.conn.execute("CREATE SCHEMA test_src")
    _db.conn.execute(
        "CREATE TABLE test_src.items (id INT, name VARCHAR)"
    )
    _db.conn.execute(
        "INSERT INTO test_src.items VALUES (1, 'a'), (2, 'b'), (3, 'c')"
    )
    yield _db
    _db.close()


@pytest.fixture
def engine(db):
    return QueryEngine(db)


def test_timeout_kills_slow_query(engine):
    result = engine.execute(
        "SELECT COUNT(*) as n FROM range(500000000) t1, range(1000) t2",
        timeout_seconds=1,
    )
    assert "error" in result
    err = result["error"].lower()
    assert "interrupt" in err or "cancel" in err


def test_timeout_none_no_interrupt(engine):
    result = engine.execute(
        "SELECT COUNT(*) as cnt FROM test_src.items",
        timeout_seconds=None,
    )
    assert "error" not in result
    assert result["rows"][0]["cnt"] == 3


def test_memory_limit_applied_and_reset(db, engine):
    result = engine.execute(
        "SELECT 1 as x",
        memory_limit="10MB",
    )
    assert "error" not in result

    # After execute(), memory_limit should be reset to the default
    row = db.conn.execute(
        "SELECT current_setting('memory_limit') as ml"
    ).fetchone()
    ml = row[0].lower()
    assert ml != "10mb", "memory_limit was not reset after query"


def test_memory_limit_none_no_change(db, engine):
    original = db.conn.execute(
        "SELECT current_setting('memory_limit') as ml"
    ).fetchone()[0]

    engine.execute("SELECT 1 as x", memory_limit=None)

    after = db.conn.execute(
        "SELECT current_setting('memory_limit') as ml"
    ).fetchone()[0]
    assert original == after
