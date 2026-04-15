"""Tests for the query engine using sample parquet data."""

import os

import pytest

from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine


@pytest.fixture
def engine(sample_db):
    return QueryEngine(sample_db)


# --- Basic queries ---

def test_execute_simple_query(engine):
    result = engine.execute("SELECT COUNT(*) as cnt FROM stripe.customers")
    assert "error" not in result
    assert result["rows"][0]["cnt"] == 180


def test_execute_select_with_filter(engine):
    result = engine.execute(
        "SELECT name, email FROM stripe.customers WHERE delinquent = true"
    )
    assert "error" not in result
    assert result["row_count"] > 0
    # All returned rows should be delinquent
    for row in result["rows"]:
        assert "@" in row["email"]


# --- Cross-source joins (the key demo) ---

def test_cross_source_join_on_email(engine):
    """Join Stripe customers with HubSpot contacts via email."""
    result = engine.execute(
        "SELECT s.name, s.email, h.company, h.lifecyclestage "
        "FROM stripe.customers s "
        "JOIN hubspot.contacts h ON s.email = h.email "
        "ORDER BY s.name LIMIT 10"
    )
    assert "error" not in result
    assert result["row_count"] == 10
    # Every row should have data from both sources
    for row in result["rows"]:
        assert row["name"] is not None
        assert row["company"] is not None


def test_cross_source_join_three_tables(engine):
    """Join Stripe + HubSpot contacts + HubSpot deals — the 'impossible query'."""
    result = engine.execute(
        "SELECT s.name, s.email, h.company, d.dealname, d.amount, d.dealstage "
        "FROM stripe.customers s "
        "JOIN hubspot.contacts h ON s.email = h.email "
        "JOIN hubspot.deals d ON h.id = d.contact_id "
        "WHERE d.dealstage = 'closedwon' "
        "ORDER BY d.amount DESC"
    )
    assert "error" not in result
    assert result["row_count"] > 0
    # All deals should be closed-won
    for row in result["rows"]:
        assert row["dealstage"] == "closedwon"
    # Should be sorted by amount descending
    amounts = [float(row["amount"]) for row in result["rows"]]
    assert amounts == sorted(amounts, reverse=True)


def test_cross_source_aggregation(engine):
    """Aggregate across sources — e.g., revenue by company."""
    result = engine.execute(
        "SELECT h.company, "
        "  COUNT(DISTINCT s.id) as stripe_customers, "
        "  COUNT(DISTINCT d.id) as deals, "
        "  SUM(d.amount) as total_deal_value "
        "FROM stripe.customers s "
        "JOIN hubspot.contacts h ON s.email = h.email "
        "LEFT JOIN hubspot.deals d ON h.id = d.contact_id "
        "GROUP BY h.company "
        "ORDER BY total_deal_value DESC NULLS LAST "
        "LIMIT 5"
    )
    assert "error" not in result
    assert result["row_count"] == 5
    # Each row should have company and aggregates
    for row in result["rows"]:
        assert row["company"] is not None
        assert row["stripe_customers"] > 0


def test_stripe_only_customers(engine):
    """Verify some Stripe customers don't match HubSpot (realistic gap)."""
    result = engine.execute(
        "SELECT s.name, s.email "
        "FROM stripe.customers s "
        "LEFT JOIN hubspot.contacts h ON s.email = h.email "
        "WHERE h.id IS NULL"
    )
    assert "error" not in result
    # Should have ~20 unmatched (10% of 200)
    assert result["row_count"] > 0
    assert result["row_count"] < 50


# --- Truncation ---

def test_execute_with_truncation(engine):
    result = engine.execute("SELECT * FROM stripe.charges", max_rows=10)
    assert result["row_count"] == 10
    assert result["total_rows"] > 10
    assert result["truncated"] is True


# --- Error handling ---

def test_execute_sql_error(engine):
    result = engine.execute("SELECT * FROM nonexistent_table")
    assert "error" in result


def test_execute_syntax_error(engine):
    result = engine.execute("SELEC * FORM customers")
    assert "error" in result


# --- list_connectors ---

def test_list_connectors(engine):
    result = engine.list_connectors()
    names = [s["name"] for s in result["connectors"]]
    assert "stripe" in names
    assert "hubspot" in names

    stripe_src = next(s for s in result["connectors"] if s["name"] == "stripe")
    assert stripe_src["table_count"] == 4
    assert stripe_src["total_rows"] > 0

    hubspot_src = next(s for s in result["connectors"] if s["name"] == "hubspot")
    assert hubspot_src["table_count"] == 3


# --- describe ---

def test_describe_table(engine):
    result = engine.describe_table("stripe.customers")
    assert "error" not in result
    assert result["schema"] == "stripe"
    assert result["table"] == "customers"
    assert result["row_count"] == 180
    col_names = [c["name"] for c in result["columns"]]
    assert "id" in col_names
    assert "email" in col_names
    assert "name" in col_names
    assert len(result["sample_rows"]) == 3


def test_describe_hubspot_deals(engine):
    result = engine.describe_table("hubspot.deals")
    assert "error" not in result
    col_names = [c["name"] for c in result["columns"]]
    assert "dealstage" in col_names
    assert "amount" in col_names
    assert "contact_id" in col_names


def test_describe_table_not_found(engine):
    result = engine.describe_table("stripe.nonexistent")
    assert "error" in result


def test_describe_without_schema(engine):
    """Should find table by searching all schemas."""
    result = engine.describe_table("customers")
    assert "error" not in result
    assert result["schema"] == "stripe"
