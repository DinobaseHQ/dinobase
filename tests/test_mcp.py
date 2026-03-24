"""Tests for the MCP server — instructions, API-derived annotations, and tools."""

import json

import pytest

from dinobase.query.engine import QueryEngine
from dinobase.mcp.server import _build_instructions


@pytest.fixture
def engine(sample_db):
    return QueryEngine(sample_db)


# --- Instructions: brief orientation, not a schema dump ---

def test_instructions_mention_source_names(engine):
    instructions = _build_instructions(engine)
    assert "stripe" in instructions
    assert "hubspot" in instructions


def test_instructions_mention_table_names(engine):
    instructions = _build_instructions(engine)
    assert "customers" in instructions
    assert "contacts" in instructions
    assert "deals" in instructions


def test_instructions_do_not_contain_columns(engine):
    """Instructions should NOT dump column-level detail — that's describe's job."""
    instructions = _build_instructions(engine)
    assert "VARCHAR" not in instructions
    assert "BIGINT" not in instructions
    assert "cents" not in instructions


def test_instructions_mention_tools(engine):
    instructions = _build_instructions(engine)
    assert "list_sources" in instructions
    assert "describe" in instructions
    assert "query" in instructions


def test_instructions_mention_joins(engine):
    instructions = _build_instructions(engine)
    assert "join" in instructions.lower()


def test_instructions_empty_db():
    """When no data is loaded, instructions should say so."""
    import os
    import tempfile
    from dinobase.db import DinobaseDB
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DINOBASE_DIR"] = tmp
        db = DinobaseDB(f"{tmp}/empty.duckdb")
        eng = QueryEngine(db)
        instructions = _build_instructions(eng)
        assert "no data" in instructions.lower()
        db.close()


# --- Annotations from Stripe OpenAPI spec (live, no hardcoding) ---

def test_stripe_annotations_from_openapi(engine):
    """Stripe column descriptions should come from the OpenAPI spec, not hardcoded."""
    result = engine.describe_table("stripe.customers")
    email_col = next((c for c in result["columns"] if c["name"] == "email"), None)
    assert email_col is not None
    # The OpenAPI spec describes the email field
    assert "description" in email_col
    assert len(email_col["description"]) > 5  # not empty


def test_stripe_created_has_timestamp_note(engine):
    """Stripe's `created` field should be annotated as unix-time from the OpenAPI spec."""
    result = engine.describe_table("stripe.customers")
    created_col = next((c for c in result["columns"] if c["name"] == "created"), None)
    assert created_col is not None
    assert "note" in created_col
    assert "timestamp" in created_col["note"].lower() or "unix" in created_col["note"].lower()


def test_stripe_amount_has_description(engine):
    """Stripe charge amounts should have a description from the spec."""
    result = engine.describe_table("stripe.charges")
    amount_col = next((c for c in result["columns"] if c["name"] == "amount"), None)
    assert amount_col is not None
    assert "description" in amount_col


def test_stripe_status_has_enum_values(engine):
    """Stripe status fields should list enum values from the spec."""
    result = engine.describe_table("stripe.subscriptions")
    status_col = next((c for c in result["columns"] if c["name"] == "status"), None)
    assert status_col is not None
    # The OpenAPI spec includes enum values for subscription status
    assert "note" in status_col
    assert "active" in status_col["note"] or "Values:" in status_col["note"]


def test_columns_without_annotations_are_clean(engine):
    """Columns without API metadata should not have empty description/note fields."""
    result = engine.describe_table("stripe.customers")
    for col in result["columns"]:
        if "description" in col:
            assert col["description"]  # not empty string
        if "note" in col:
            assert col["note"]  # not empty string


# --- HubSpot without annotations (no API key in tests) ---

def test_hubspot_describe_works_without_annotations(engine):
    """HubSpot columns should still be described even without API-derived annotations."""
    result = engine.describe_table("hubspot.contacts")
    assert "error" not in result
    assert result["row_count"] == 180
    col_names = [c["name"] for c in result["columns"]]
    assert "email" in col_names
    assert "firstname" in col_names


# --- Tools ---

def test_mcp_server_creatable():
    from dinobase.mcp.server import _create_server, _build_instructions
    assert callable(_create_server)
    assert callable(_build_instructions)


def test_query_returns_valid_json(engine):
    result = engine.execute("SELECT name, email FROM stripe.customers LIMIT 3")
    json_str = json.dumps(result, default=str)
    parsed = json.loads(json_str)
    assert parsed["row_count"] == 3


def test_cross_source_query(engine):
    result = engine.execute(
        "SELECT s.name, h.company, d.amount, d.dealstage "
        "FROM stripe.customers s "
        "JOIN hubspot.contacts h ON s.email = h.email "
        "JOIN hubspot.deals d ON h.id = d.contact_id "
        "WHERE d.dealstage = 'closedwon' "
        "ORDER BY d.amount DESC LIMIT 5"
    )
    assert "error" not in result
    assert result["row_count"] > 0


def test_list_sources_returns_both(engine):
    result = engine.list_sources()
    names = {s["name"] for s in result["sources"]}
    assert names == {"stripe", "hubspot"}


def test_describe_returns_sample_rows(engine):
    result = engine.describe_table("hubspot.contacts")
    assert len(result["sample_rows"]) == 3
    assert "email" in result["sample_rows"][0]
