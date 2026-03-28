"""Tests for the mutation engine — multi-row, multi-statement, cross-source."""

import json
import os

import pytest

from dinobase.db import DinobaseDB, META_SCHEMA
from dinobase.query.engine import QueryEngine
from dinobase.query.mutations import MutationEngine, _parse_mutation_sql, _split_statements


@pytest.fixture
def db(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    db = DinobaseDB(tmp_path / "test.duckdb")

    # Create two sources for cross-source testing
    db.conn.execute("CREATE SCHEMA hubspot")
    db.conn.execute(
        "CREATE TABLE hubspot.deals (id VARCHAR, dealname VARCHAR, amount DOUBLE, dealstage VARCHAR)"
    )
    db.conn.execute(
        "INSERT INTO hubspot.deals VALUES "
        "('9001', 'Acme - New Business', 50000, 'proposal'), "
        "('9002', 'Globex - Renewal', 30000, 'qualified'), "
        "('9003', 'Initech - Expansion', 75000, 'closedwon'), "
        "('9004', 'Wayne - Upsell', 90000, 'proposal'), "
        "('9005', 'Stark - New Business', 120000, 'qualified')"
    )

    db.conn.execute("CREATE SCHEMA stripe")
    db.conn.execute(
        "CREATE TABLE stripe.customers (id VARCHAR, email VARCHAR, name VARCHAR, delinquent BOOLEAN)"
    )
    db.conn.execute(
        "INSERT INTO stripe.customers VALUES "
        "('cus_1', 'alice@acme.com', 'Alice', false), "
        "('cus_2', 'bob@globex.com', 'Bob', true), "
        "('cus_3', 'carol@initech.com', 'Carol', false)"
    )

    from dinobase.config import add_source
    add_source("hubspot", "hubspot", {"api_key": "test"})
    add_source("stripe", "stripe", {"api_key": "test"})

    yield db
    db.close()


@pytest.fixture
def engine(db):
    return QueryEngine(db)


@pytest.fixture
def mutation_engine(db):
    return MutationEngine(db)


# --- SQL parsing ---

def test_parse_update():
    result = _parse_mutation_sql("UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'")
    assert result["operation"] == "UPDATE"
    assert result["schema"] == "hubspot"
    assert result["table"] == "deals"


def test_parse_insert():
    result = _parse_mutation_sql(
        "INSERT INTO hubspot.deals (id, dealname, amount) VALUES ('9999', 'Test', '10000')"
    )
    assert result["operation"] == "INSERT"
    assert result["columns"] == ["id", "dealname", "amount"]


def test_parse_delete():
    result = _parse_mutation_sql("DELETE FROM hubspot.deals WHERE id = '9001'")
    assert result["operation"] == "DELETE"
    assert result["schema"] == "hubspot"
    assert result["table"] == "deals"
    assert result["where"] == "id = '9001'"


def test_delete_requires_where():
    result = _parse_mutation_sql("DELETE FROM hubspot.deals")
    assert "error" in result
    assert "WHERE" in result["error"]


def test_block_drop():
    result = _parse_mutation_sql("DROP TABLE hubspot.deals")
    assert "error" in result


def test_split_statements():
    stmts = _split_statements(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'; "
        "UPDATE stripe.customers SET delinquent = true WHERE id = 'cus_1'"
    )
    assert len(stmts) == 2
    assert "hubspot" in stmts[0]
    assert "stripe" in stmts[1]


def test_split_single_statement():
    stmts = _split_statements("UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'")
    assert len(stmts) == 1


def test_split_ignores_empty():
    stmts = _split_statements("UPDATE hubspot.deals SET dealstage = 'x' WHERE id = '1'; ;; ")
    assert len(stmts) == 1


# --- Single-row update ---

def test_single_row_update_preview(mutation_engine):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'"
    )
    assert result["status"] == "pending_confirmation"
    assert result["preview"]["rows_affected"] == 1
    assert len(result["preview"]["changes"]) == 1
    assert "proposal → closedwon" in result["preview"]["changes"][0]["dealstage"]


def test_single_row_confirm(mutation_engine, db):
    preview = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'"
    )
    result = mutation_engine.confirm(preview["mutation_id"])
    assert result["status"] == "executed"

    rows = db.query("SELECT dealstage FROM hubspot.deals WHERE id = '9001'")
    assert rows[0]["dealstage"] == "closedwon"


# --- Multi-row update ---

def test_multi_row_update_preview(mutation_engine):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE dealstage = 'proposal'"
    )
    assert result["status"] == "pending_confirmation"
    assert result["preview"]["rows_affected"] == 2  # 9001 and 9004
    assert len(result["preview"]["changes"]) == 2

    ids = [c["id"] for c in result["preview"]["changes"]]
    assert "9001" in ids
    assert "9004" in ids


def test_multi_row_confirm(mutation_engine, db):
    preview = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE dealstage = 'proposal'"
    )
    result = mutation_engine.confirm(preview["mutation_id"])
    assert result["status"] == "executed"

    rows = db.query(
        "SELECT id, dealstage FROM hubspot.deals WHERE id IN ('9001', '9004') ORDER BY id"
    )
    assert all(r["dealstage"] == "closedwon" for r in rows)


def test_multi_row_too_many(mutation_engine):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon'",  # all 5 rows
        max_affected_rows=3,
    )
    assert "error" in result
    assert "5 rows" in result["error"]


# --- Multi-statement SQL ---

def test_multi_statement_preview(mutation_engine):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'; "
        "UPDATE stripe.customers SET delinquent = false WHERE id = 'cus_2'"
    )
    assert "batch_id" in result
    assert result["status"] == "pending_confirmation"
    assert result["statements"] == 2
    assert result["valid"] == 2
    assert len(result["mutations"]) == 2

    sources = result["sources_involved"]
    assert "hubspot" in sources
    assert "stripe" in sources


def test_multi_statement_has_mutation_ids(mutation_engine):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'; "
        "UPDATE stripe.customers SET delinquent = false WHERE id = 'cus_2'"
    )
    mutation_ids = [m["mutation_id"] for m in result["mutations"]]
    assert len(mutation_ids) == 2
    assert all(mid.startswith("mut_") for mid in mutation_ids)


def test_multi_statement_confirm_individually(mutation_engine, db):
    batch = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'; "
        "UPDATE stripe.customers SET delinquent = false WHERE id = 'cus_2'"
    )
    for m in batch["mutations"]:
        result = mutation_engine.confirm(m["mutation_id"])
        assert result["status"] == "executed"

    assert db.query("SELECT dealstage FROM hubspot.deals WHERE id = '9001'")[0]["dealstage"] == "closedwon"
    assert db.query("SELECT delinquent FROM stripe.customers WHERE id = 'cus_2'")[0]["delinquent"] is False


def test_multi_statement_confirm_batch(mutation_engine, db):
    batch = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9002'; "
        "UPDATE stripe.customers SET delinquent = false WHERE id = 'cus_2'"
    )
    mutation_ids = [m["mutation_id"] for m in batch["mutations"]]

    result = mutation_engine.confirm_batch(mutation_ids)
    assert result["status"] == "batch_executed"
    assert result["succeeded"] == 2
    assert result["failed"] == 0


def test_multi_statement_partial_error(mutation_engine):
    """One valid statement + one invalid should return partial results."""
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'; "
        "DROP TABLE stripe.customers"
    )
    # First is valid, second is blocked
    assert result["valid"] == 1
    assert len(result["errors"]) == 1
    assert "not allowed" in result["errors"][0]["error"].lower()


# --- Cross-source in single statement ---

def test_cross_source_preview_shows_both(mutation_engine):
    """Multi-statement spanning two sources should list both in sources_involved."""
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET amount = 60000 WHERE id = '9001'; "
        "INSERT INTO stripe.customers (id, email, name, delinquent) VALUES ('cus_99', 'new@test.com', 'New', 'false')"
    )
    assert set(result["sources_involved"]) == {"hubspot", "stripe"}


# --- Edge cases ---

def test_update_no_matching_rows(mutation_engine):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = 'nonexistent'"
    )
    assert "error" in result


def test_update_unknown_schema(mutation_engine):
    result = mutation_engine.handle_sql(
        "UPDATE nonexistent.deals SET dealstage = 'closedwon' WHERE id = '9001'"
    )
    assert "error" in result


def test_confirm_nonexistent(mutation_engine):
    result = mutation_engine.confirm("mut_doesnotexist")
    assert "error" in result


def test_confirm_already_executed(mutation_engine):
    preview = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9003'"
    )
    mutation_engine.confirm(preview["mutation_id"])
    result = mutation_engine.confirm(preview["mutation_id"])
    assert "error" in result
    assert "not pending" in result["error"].lower()


def test_cancel(mutation_engine, db):
    preview = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'"
    )
    mutation_engine.cancel(preview["mutation_id"])

    rows = db.query("SELECT dealstage FROM hubspot.deals WHERE id = '9001'")
    assert rows[0]["dealstage"] == "proposal"  # unchanged


# --- Audit log ---

def test_mutation_logged(mutation_engine, db):
    preview = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'"
    )
    mutation_engine.confirm(preview["mutation_id"])

    rows = db.query(
        f"SELECT * FROM {META_SCHEMA}.mutations WHERE mutation_id = '{preview['mutation_id']}'"
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "executed"
    assert rows[0]["source_name"] == "hubspot"
    assert rows[0]["operation"] == "UPDATE"


# --- Integration with QueryEngine ---

def test_query_engine_routes_mutations(engine):
    result = engine.execute("UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'")
    assert "mutation_id" in result
    assert result["status"] == "pending_confirmation"


def test_query_engine_routes_multi_statement(engine):
    result = engine.execute(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'; "
        "UPDATE stripe.customers SET delinquent = true WHERE id = 'cus_1'"
    )
    assert "batch_id" in result
    assert len(result["mutations"]) == 2


def test_query_engine_routes_delete(engine):
    result = engine.execute("DELETE FROM hubspot.deals WHERE id = '9001'")
    assert "mutation_id" in result
    assert result["status"] == "pending_confirmation"
    assert result["preview"]["operation"] == "DELETE"


def test_query_engine_select_still_works(engine):
    result = engine.execute("SELECT * FROM hubspot.deals ORDER BY id")
    assert "rows" in result
    assert result["row_count"] == 5


# --- DELETE operations ---

def test_single_row_delete_preview(mutation_engine):
    result = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE id = '9001'"
    )
    assert result["status"] == "pending_confirmation"
    assert result["preview"]["operation"] == "DELETE"
    assert result["preview"]["rows_affected"] == 1
    assert len(result["preview"]["rows_to_delete"]) == 1
    assert result["preview"]["rows_to_delete"][0]["id"] == "9001"


def test_single_row_delete_confirm(mutation_engine, db):
    preview = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE id = '9001'"
    )
    result = mutation_engine.confirm(preview["mutation_id"])
    assert result["status"] == "executed"

    rows = db.query("SELECT * FROM hubspot.deals WHERE id = '9001'")
    assert len(rows) == 0

    # Other rows still exist
    remaining = db.query("SELECT COUNT(*) as cnt FROM hubspot.deals")
    assert remaining[0]["cnt"] == 4


def test_multi_row_delete_preview(mutation_engine):
    result = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE dealstage = 'proposal'"
    )
    assert result["status"] == "pending_confirmation"
    assert result["preview"]["rows_affected"] == 2
    assert len(result["preview"]["rows_to_delete"]) == 2

    ids = [r["id"] for r in result["preview"]["rows_to_delete"]]
    assert "9001" in ids
    assert "9004" in ids


def test_multi_row_delete_confirm(mutation_engine, db):
    preview = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE dealstage = 'proposal'"
    )
    result = mutation_engine.confirm(preview["mutation_id"])
    assert result["status"] == "executed"

    rows = db.query("SELECT * FROM hubspot.deals WHERE dealstage = 'proposal'")
    assert len(rows) == 0

    remaining = db.query("SELECT COUNT(*) as cnt FROM hubspot.deals")
    assert remaining[0]["cnt"] == 3


def test_delete_too_many_rows(mutation_engine):
    result = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE amount > 0",
        max_affected_rows=2,
    )
    assert "error" in result
    assert "5 rows" in result["error"]


def test_delete_no_matching_rows(mutation_engine):
    result = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE id = 'nonexistent'"
    )
    assert "error" in result


def test_delete_unknown_schema(mutation_engine):
    result = mutation_engine.handle_sql(
        "DELETE FROM nonexistent.deals WHERE id = '9001'"
    )
    assert "error" in result


def test_delete_audit_log(mutation_engine, db):
    preview = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE id = '9001'"
    )
    mutation_engine.confirm(preview["mutation_id"])

    rows = db.query(
        f"SELECT * FROM {META_SCHEMA}.mutations WHERE mutation_id = '{preview['mutation_id']}'"
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "executed"
    assert rows[0]["operation"] == "DELETE"
    assert rows[0]["source_name"] == "hubspot"


def test_multi_statement_with_delete(mutation_engine):
    """Mixed batch: UPDATE + DELETE should both generate previews."""
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9002'; "
        "DELETE FROM hubspot.deals WHERE id = '9001'"
    )
    assert "batch_id" in result
    assert result["valid"] == 2
    assert len(result["mutations"]) == 2

    ops = [m["preview"]["operation"] for m in result["mutations"]]
    assert "UPDATE" in ops
    assert "DELETE" in ops


# --- --force flag ---

def test_force_skips_confirmation(mutation_engine, db):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001' --force"
    )
    assert result["status"] == "executed"

    rows = db.query("SELECT dealstage FROM hubspot.deals WHERE id = '9001'")
    assert rows[0]["dealstage"] == "closedwon"


def test_force_delete(mutation_engine, db):
    result = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals WHERE id = '9001' --force"
    )
    assert result["status"] == "executed"

    rows = db.query("SELECT * FROM hubspot.deals WHERE id = '9001'")
    assert len(rows) == 0


def test_force_batch(mutation_engine, db):
    result = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9002'; "
        "DELETE FROM hubspot.deals WHERE id = '9001' --force"
    )
    assert result["status"] == "batch_executed"
    assert result["succeeded"] == 2


def test_force_with_error_still_returns_error(mutation_engine):
    result = mutation_engine.handle_sql(
        "DELETE FROM hubspot.deals --force"
    )
    assert "error" in result


# --- TTL expiration ---

def test_pending_mutations_expire(mutation_engine, db):
    """Pending mutations older than TTL should be auto-expired."""
    preview = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'"
    )
    mutation_id = preview["mutation_id"]

    # Backdate the created_at to simulate an old mutation
    db.conn.execute(
        f"UPDATE {META_SCHEMA}.mutations SET created_at = current_timestamp - INTERVAL '20 minutes' "
        f"WHERE mutation_id = ?",
        [mutation_id],
    )

    # Trying to confirm should fail — it's expired
    result = mutation_engine.confirm(mutation_id)
    assert "error" in result
    assert "expired" in result["error"].lower()


def test_fresh_mutations_not_expired(mutation_engine):
    """Mutations within TTL should not be expired."""
    preview = mutation_engine.handle_sql(
        "UPDATE hubspot.deals SET dealstage = 'closedwon' WHERE id = '9001'"
    )
    # Confirm immediately — should work fine
    result = mutation_engine.confirm(preview["mutation_id"])
    assert result["status"] == "executed"
