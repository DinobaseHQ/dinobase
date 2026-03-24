"""Tests for the parquet/file source connector."""

import os
from pathlib import Path

import pytest

from dinobase.db import DinobaseDB
from dinobase.sync.sources.parquet import add_file_source, extract_metadata
from dinobase.query.engine import QueryEngine

SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"


@pytest.fixture
def db(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    db = DinobaseDB(tmp_path / "test.duckdb")
    yield db
    db.close()


def test_add_directory(db):
    """Adding a directory should create views for all parquet files in it."""
    result = add_file_source(db, "demo", str(SAMPLE_DATA_DIR))
    assert result["total_rows"] > 0
    table_names = [t["name"] for t in result["tables"]]
    assert "customers" in table_names
    assert "contacts" in table_names
    assert "deals" in table_names
    assert "charges" in table_names


def test_add_single_file(db):
    """Adding a single file should create one view."""
    path = str(SAMPLE_DATA_DIR / "stripe_customers.parquet")
    result = add_file_source(db, "stripe", path)
    assert len(result["tables"]) == 1
    assert result["tables"][0]["name"] == "customers"
    assert result["tables"][0]["rows"] == 180


def test_views_are_queryable(db):
    """Views created from parquet should be queryable like regular tables."""
    add_file_source(db, "demo", str(SAMPLE_DATA_DIR))
    rows = db.query("SELECT COUNT(*) as cnt FROM demo.customers")
    assert rows[0]["cnt"] == 180


def test_cross_source_join_via_views(db):
    """Cross-source joins should work across parquet views."""
    add_file_source(db, "demo", str(SAMPLE_DATA_DIR))
    rows = db.query(
        "SELECT c.name, h.company, d.amount "
        "FROM demo.customers c "
        "JOIN demo.contacts h ON c.email = h.email "
        "JOIN demo.deals d ON h.id = d.contact_id "
        "WHERE d.dealstage = 'closedwon' "
        "ORDER BY d.amount DESC LIMIT 3"
    )
    assert len(rows) == 3
    assert float(rows[0]["amount"]) > 0


def test_metadata_extraction(db):
    """Parquet source should infer basic column annotations."""
    add_file_source(db, "demo", str(SAMPLE_DATA_DIR))
    db.update_table_metadata("demo", "demo")

    annotations = extract_metadata(db, "demo")
    # Should detect email as a join key
    customers_ann = annotations.get("customers", {})
    email_ann = customers_ann.get("email", {})
    assert "join" in email_ann.get("note", "").lower()

    # Should detect *_id columns
    deals_ann = annotations.get("deals", {})
    contact_id_ann = deals_ann.get("contact_id", {})
    assert "foreign key" in contact_id_ann.get("description", "").lower()


def test_describe_parquet_table(db):
    """describe() should work on parquet-backed views."""
    add_file_source(db, "demo", str(SAMPLE_DATA_DIR))
    db.update_table_metadata("demo", "demo")

    engine = QueryEngine(db)
    result = engine.describe_table("demo.customers")
    assert result["row_count"] == 180
    col_names = [c["name"] for c in result["columns"]]
    assert "email" in col_names
    assert "name" in col_names
    assert len(result["sample_rows"]) == 3


def test_list_sources_includes_parquet(db):
    """list_sources should show parquet-backed sources."""
    add_file_source(db, "demo", str(SAMPLE_DATA_DIR))
    db.log_sync_start("demo", "parquet")
    db.log_sync_end(1, "success", tables_synced=7, rows_synced=1385)
    db.update_table_metadata("demo", "demo")

    engine = QueryEngine(db)
    result = engine.list_sources()
    names = [s["name"] for s in result["sources"]]
    assert "demo" in names
    demo = next(s for s in result["sources"] if s["name"] == "demo")
    assert demo["total_rows"] > 0


def test_no_files_raises(db):
    """Should raise if no files found at path."""
    with pytest.raises(ValueError, match="No parquet files"):
        add_file_source(db, "empty", "/nonexistent/path/")


def test_table_name_cleanup(db):
    """File names should be cleaned into valid table names."""
    from dinobase.sync.sources.parquet import _path_to_table_name
    assert _path_to_table_name("/data/stripe_customers.parquet") == "customers"
    assert _path_to_table_name("/data/hubspot_contacts.parquet") == "contacts"
    assert _path_to_table_name("/data/my-export-2024.parquet") == "my_export_2024"
    assert _path_to_table_name("events.parquet") == "events"
