"""Shared test fixtures using sample parquet data."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from dinobase.db import DinobaseDB

SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"


@pytest.fixture(scope="session", autouse=True)
def isolate_cloud_credentials(tmp_path_factory):
    """Prevent tests from reading real cloud credentials from ~/.dinobase."""
    creds_dir = tmp_path_factory.mktemp("credentials")
    os.environ["DINOBASE_CREDENTIALS_DIR"] = str(creds_dir)
    yield
    os.environ.pop("DINOBASE_CREDENTIALS_DIR", None)


@pytest.fixture(scope="session", autouse=True)
def generate_sample_data():
    """Generate sample parquet files if they don't exist."""
    stripe_files = [
        SAMPLE_DATA_DIR / "stripe_customers.parquet",
        SAMPLE_DATA_DIR / "stripe_subscriptions.parquet",
        SAMPLE_DATA_DIR / "stripe_charges.parquet",
        SAMPLE_DATA_DIR / "stripe_invoices.parquet",
    ]
    if not all(f.exists() for f in stripe_files):
        script = Path(__file__).parent.parent / "scripts" / "generate_sample_data.py"
        subprocess.run([sys.executable, str(script)], check=True)


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
