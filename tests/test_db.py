"""Tests for the DuckDB storage layer."""

import os
import tempfile

import pytest

from dinobase.db import DinobaseDB, META_SCHEMA


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.duckdb"
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    db = DinobaseDB(db_path)
    yield db
    db.close()


def test_init_creates_metadata_tables(db):
    """Metadata tables should be created on first access."""
    _ = db.conn  # triggers init
    tables = db.query(
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{META_SCHEMA}' ORDER BY table_name"
    )
    table_names = [t["table_name"] for t in tables]
    assert "sync_log" in table_names
    assert "tables" in table_names
    assert "columns" in table_names


def test_log_sync_lifecycle(db):
    """Test sync logging start and end."""
    sync_id = db.log_sync_start("test_source", "stripe")
    assert sync_id >= 1

    db.log_sync_end(sync_id, "success", tables_synced=3, rows_synced=100)

    rows = db.query(f"SELECT * FROM {META_SCHEMA}.sync_log WHERE id = {sync_id}")
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["tables_synced"] == 3
    assert rows[0]["rows_synced"] == 100
    assert rows[0]["finished_at"] is not None


def test_log_sync_error(db):
    sync_id = db.log_sync_start("test_source", "stripe")
    db.log_sync_end(sync_id, "error", error_message="Connection refused")

    rows = db.query(f"SELECT * FROM {META_SCHEMA}.sync_log WHERE id = {sync_id}")
    assert rows[0]["status"] == "error"
    assert rows[0]["error_message"] == "Connection refused"


def test_schema_and_table_operations(db):
    """Test creating schemas and querying metadata."""
    db.conn.execute("CREATE SCHEMA test_source")
    db.conn.execute(
        "CREATE TABLE test_source.users (id INTEGER, name VARCHAR, email VARCHAR)"
    )
    db.conn.execute(
        "INSERT INTO test_source.users VALUES (1, 'Alice', 'alice@example.com'), "
        "(2, 'Bob', 'bob@example.com')"
    )

    schemas = db.get_schemas()
    assert "test_source" in schemas

    tables = db.get_tables("test_source")
    assert "users" in tables

    columns = db.get_columns("test_source", "users")
    col_names = [c["column_name"] for c in columns]
    assert "id" in col_names
    assert "name" in col_names
    assert "email" in col_names

    count = db.get_row_count("test_source", "users")
    assert count == 2


def test_update_table_metadata(db):
    """Test that update_table_metadata refreshes _dinobase metadata."""
    db.conn.execute("CREATE SCHEMA my_source")
    db.conn.execute(
        "CREATE TABLE my_source.orders (id INTEGER, amount DECIMAL, created_at TIMESTAMP)"
    )
    db.conn.execute(
        "INSERT INTO my_source.orders VALUES (1, 99.99, '2026-01-01'), (2, 149.50, '2026-01-02')"
    )
    # Also create a dlt internal table that should be skipped
    db.conn.execute("CREATE TABLE my_source._dlt_loads (load_id VARCHAR)")

    db.update_table_metadata("my_source", "my_source")

    # Check _dinobase.tables
    rows = db.query(
        f"SELECT * FROM {META_SCHEMA}.tables WHERE source_name = 'my_source'"
    )
    assert len(rows) == 1  # _dlt_loads should be skipped
    assert rows[0]["table_name"] == "orders"
    assert rows[0]["row_count"] == 2

    # Check _dinobase.columns
    cols = db.query(
        f"SELECT * FROM {META_SCHEMA}.columns "
        f"WHERE source_name = 'my_source' AND table_name = 'orders' "
        f"ORDER BY column_name"
    )
    assert len(cols) == 3
    col_names = [c["column_name"] for c in cols]
    assert "id" in col_names
    assert "amount" in col_names
    assert "created_at" in col_names


def test_query_returns_dicts(db):
    db.conn.execute("CREATE TABLE main.test_data (x INTEGER, y VARCHAR)")
    db.conn.execute("INSERT INTO main.test_data VALUES (1, 'a'), (2, 'b')")

    rows = db.query("SELECT * FROM main.test_data ORDER BY x")
    assert len(rows) == 2
    assert rows[0] == {"x": 1, "y": "a"}
    assert rows[1] == {"x": 2, "y": "b"}


def test_log_sync_start_uses_sequence(db):
    """log_sync_start must use the sequence, not MAX(id)+1."""
    id1 = db.log_sync_start("source_a", "stripe")
    id2 = db.log_sync_start("source_b", "stripe")
    id3 = db.log_sync_start("source_a", "stripe")

    # IDs should be unique and monotonically increasing
    assert id1 != id2 != id3
    assert id2 > id1
    assert id3 > id2


def test_log_sync_start_no_collision_after_delete(db):
    """Sequence must not reset to 1 if rows are deleted (avoids PK collision)."""
    id1 = db.log_sync_start("source_a", "stripe")
    db.meta_conn.execute(f"DELETE FROM {META_SCHEMA}.sync_log WHERE id = {id1}")

    id2 = db.log_sync_start("source_b", "stripe")
    # If MAX(id)+1 were used, id2 would be 1 (collision). With sequence it's 2.
    assert id2 > id1
