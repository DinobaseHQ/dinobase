"""Tests for the semantic layer auto-annotation agent."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dinobase.annotations import RelationshipInput, apply_relationship
from dinobase.db import DinobaseDB
from dinobase.semantic_agent import (
    SemanticAgent,
    detect_relationships_heuristic,
    is_source_annotated,
    spawn_semantic_agent,
)


@pytest.fixture
def fresh_db(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    db = DinobaseDB(tmp_path / "test.duckdb")

    # Stripe-like schema with FK columns
    db.conn.execute("CREATE SCHEMA stripe")
    db.conn.execute("CREATE TABLE stripe.customers (id VARCHAR, email VARCHAR, name VARCHAR)")
    db.conn.execute(
        "CREATE TABLE stripe.subscriptions "
        "(id VARCHAR, customer_id VARCHAR, plan_id VARCHAR, status VARCHAR)"
    )
    db.conn.execute("CREATE TABLE stripe.plans (id VARCHAR, name VARCHAR, amount INTEGER)")

    # Register in _dinobase.tables so the agent knows about them
    db.conn.execute(
        "INSERT INTO _dinobase.tables (connector_name, schema_name, table_name, row_count) VALUES "
        "('stripe','stripe','customers',10),"
        "('stripe','stripe','subscriptions',5),"
        "('stripe','stripe','plans',3)"
    )

    yield db
    db.close()


# ---------------------------------------------------------------------------
# is_source_annotated
# ---------------------------------------------------------------------------


def test_not_annotated_when_no_relationships(fresh_db):
    assert is_source_annotated(fresh_db, "stripe") is False


def test_not_annotated_when_missing_table_description(fresh_db):
    # Add a relationship but leave tables undescribed
    apply_relationship(
        fresh_db,
        RelationshipInput(
            from_table="stripe.subscriptions",
            from_column="customer_id",
            to_table="stripe.customers",
            to_column="id",
        ),
    )
    assert is_source_annotated(fresh_db, "stripe") is False


def test_annotated_when_relationships_and_all_descriptions(fresh_db):
    apply_relationship(
        fresh_db,
        RelationshipInput(
            from_table="stripe.subscriptions",
            from_column="customer_id",
            to_table="stripe.customers",
            to_column="id",
        ),
    )
    for table in ["customers", "subscriptions", "plans"]:
        fresh_db.set_table_description("stripe", table, f"{table} description")

    assert is_source_annotated(fresh_db, "stripe") is True


# ---------------------------------------------------------------------------
# detect_relationships_heuristic
# ---------------------------------------------------------------------------


def test_heuristic_detects_customer_id(fresh_db):
    rels = detect_relationships_heuristic(fresh_db, "stripe")
    targets = {(r.from_table, r.from_column, r.to_table, r.to_column) for r in rels}
    assert ("stripe.subscriptions", "customer_id", "stripe.customers", "id") in targets


def test_heuristic_detects_plan_id(fresh_db):
    rels = detect_relationships_heuristic(fresh_db, "stripe")
    targets = {(r.from_table, r.from_column, r.to_table, r.to_column) for r in rels}
    assert ("stripe.subscriptions", "plan_id", "stripe.plans", "id") in targets


def test_heuristic_skips_dlt_tables(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    db = DinobaseDB(tmp_path / "dlt.duckdb")
    db.conn.execute("CREATE SCHEMA src")
    db.conn.execute("CREATE TABLE src._dlt_loads (load_id VARCHAR, schema_name VARCHAR)")
    db.conn.execute("CREATE TABLE src.items (id VARCHAR, _dlt_load_id VARCHAR)")
    db.conn.execute(
        "INSERT INTO _dinobase.tables (connector_name, schema_name, table_name, row_count) VALUES "
        "('src','src','_dlt_loads',1),('src','src','items',5)"
    )
    rels = detect_relationships_heuristic(db, "src")
    # Should not try to match _dlt_load_id → _dlt_loads (dlt table is filtered out)
    targets = {r.to_table for r in rels}
    assert "src._dlt_loads" not in targets
    db.close()


def test_heuristic_no_false_positives_when_no_matching_table(fresh_db):
    # order_id has no "orders" table — should not generate a relationship
    fresh_db.conn.execute("ALTER TABLE stripe.subscriptions ADD COLUMN order_id VARCHAR")
    rels = detect_relationships_heuristic(fresh_db, "stripe")
    targets = {(r.from_column, r.to_table) for r in rels}
    assert not any("order" in to for _, to in targets)


def test_heuristic_cardinality_is_one_to_many(fresh_db):
    rels = detect_relationships_heuristic(fresh_db, "stripe")
    for rel in rels:
        assert rel.cardinality == "one_to_many"


# ---------------------------------------------------------------------------
# spawn_semantic_agent kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_prevents_thread_spawn(monkeypatch, fresh_db):
    monkeypatch.setenv("DINOBASE_AUTO_ANNOTATE", "false")
    with patch("dinobase.semantic_agent.threading.Thread") as mock_thread:
        spawn_semantic_agent("stripe")
        mock_thread.assert_not_called()


def test_kill_switch_values(monkeypatch, fresh_db):
    for val in ("0", "no", "off", "False", "FALSE"):
        monkeypatch.setenv("DINOBASE_AUTO_ANNOTATE", val)
        with patch("dinobase.semantic_agent.threading.Thread") as mock_thread:
            spawn_semantic_agent("stripe")
            mock_thread.assert_not_called()


def test_enabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("DINOBASE_AUTO_ANNOTATE", raising=False)
    monkeypatch.setenv("DINOBASE_DIR", str(tmp_path))
    with patch("dinobase.semantic_agent.threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()
        spawn_semantic_agent("stripe")
        mock_thread.assert_called_once()


# ---------------------------------------------------------------------------
# SemanticAgent.run — skips if already annotated
# ---------------------------------------------------------------------------


def test_agent_skips_fully_annotated_source(fresh_db):
    # Set up fully annotated source
    apply_relationship(
        fresh_db,
        RelationshipInput(
            from_table="stripe.subscriptions",
            from_column="customer_id",
            to_table="stripe.customers",
            to_column="id",
        ),
    )
    for table in ["customers", "subscriptions", "plans"]:
        fresh_db.set_table_description("stripe", table, f"{table} description")

    with patch("dinobase.semantic_agent.detect_relationships_heuristic") as mock_heuristic:
        SemanticAgent(fresh_db, "stripe").run()
        mock_heuristic.assert_not_called()


# ---------------------------------------------------------------------------
# SemanticAgent.run — heuristic writes relationships
# ---------------------------------------------------------------------------


def test_agent_writes_heuristic_relationships(fresh_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    SemanticAgent(fresh_db, "stripe").run()

    rels = fresh_db.get_relationships("stripe", "subscriptions")
    assert len(rels) >= 1


# ---------------------------------------------------------------------------
# SemanticAgent.run — Claude agent called when API key present (mocked)
# ---------------------------------------------------------------------------


def test_agent_calls_claude_when_api_key_set(fresh_db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    with patch.dict("sys.modules", {"anthropic": MagicMock()}):
        with patch("dinobase.semantic_agent.run_claude_agent") as mock_claude:
            SemanticAgent(fresh_db, "stripe").run()
            mock_claude.assert_called_once_with(fresh_db, "stripe", "sk-test-key")


def test_agent_skips_claude_when_no_api_key(fresh_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch("dinobase.semantic_agent.run_claude_agent") as mock_claude:
        SemanticAgent(fresh_db, "stripe").run()
        mock_claude.assert_not_called()


# ---------------------------------------------------------------------------
# SemanticAgent.run — never raises
# ---------------------------------------------------------------------------


def test_agent_never_raises_on_error(fresh_db):
    with patch("dinobase.semantic_agent.detect_relationships_heuristic", side_effect=RuntimeError("boom")):
        # Should log to stderr but not raise
        SemanticAgent(fresh_db, "stripe").run()
