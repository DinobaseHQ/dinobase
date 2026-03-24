"""Shared test fixtures using sample parquet data."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dinobase.db import DinobaseDB

SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"


@pytest.fixture
def sample_db(tmp_path):
    """Create a DinobaseDB loaded with sample Stripe + HubSpot parquet data.

    Stripe annotations come from Stripe's public OpenAPI spec (live fetch).
    HubSpot annotations are skipped (requires auth) — tests that need them
    should mock or set annotations directly.
    """
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    db = DinobaseDB(tmp_path / "test.duckdb")

    # Load Stripe data
    db.conn.execute("CREATE SCHEMA stripe")
    stripe_tables = []
    for table in ["customers", "subscriptions", "charges", "invoices"]:
        parquet_path = SAMPLE_DATA_DIR / f"stripe_{table}.parquet"
        if parquet_path.exists():
            db.conn.execute(
                f"CREATE TABLE stripe.{table} AS "
                f"SELECT * FROM read_parquet('{parquet_path}')"
            )
            stripe_tables.append(table)

    # Load HubSpot data
    db.conn.execute("CREATE SCHEMA hubspot")
    hubspot_tables = []
    for table in ["contacts", "companies", "deals"]:
        parquet_path = SAMPLE_DATA_DIR / f"hubspot_{table}.parquet"
        if parquet_path.exists():
            db.conn.execute(
                f"CREATE TABLE hubspot.{table} AS "
                f"SELECT * FROM read_parquet('{parquet_path}')"
            )
            hubspot_tables.append(table)

    # Extract Stripe metadata from OpenAPI spec (public, no auth needed)
    from dinobase.sync.metadata import extract_stripe_metadata
    stripe_annotations = extract_stripe_metadata("", stripe_tables)

    # Record sync metadata with annotations
    sync_id = db.log_sync_start("stripe", "stripe")
    db.log_sync_end(sync_id, "success", tables_synced=len(stripe_tables), rows_synced=984)
    db.update_table_metadata("stripe", "stripe", annotations=stripe_annotations)

    sync_id = db.log_sync_start("hubspot", "hubspot")
    db.log_sync_end(sync_id, "success", tables_synced=len(hubspot_tables), rows_synced=401)
    db.update_table_metadata("hubspot", "hubspot")  # no annotations (would need auth)

    yield db
    db.close()
