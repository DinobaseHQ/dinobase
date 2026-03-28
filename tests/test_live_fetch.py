"""Tests for transparent live fetch — SQL pattern detection, fetch client, and integration."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from dinobase.query.engine import _detect_id_lookup, QueryEngine


# ---------------------------------------------------------------------------
# SQL pattern detection
# ---------------------------------------------------------------------------

class TestDetectIdLookup:
    def test_simple_string_id(self):
        result = _detect_id_lookup("SELECT * FROM intercom.contacts WHERE id = '12345'")
        assert result == ("intercom", "contacts", "12345")

    def test_numeric_id(self):
        result = _detect_id_lookup("SELECT * FROM stripe.charges WHERE id = 99")
        assert result == ("stripe", "charges", "99")

    def test_quoted_identifiers(self):
        result = _detect_id_lookup('SELECT * FROM "stripe"."customers" WHERE "id" = \'cus_123\'')
        assert result == ("stripe", "customers", "cus_123")

    def test_select_specific_columns(self):
        result = _detect_id_lookup("SELECT name, email FROM intercom.contacts WHERE id = 'abc'")
        assert result == ("intercom", "contacts", "abc")

    def test_with_semicolon(self):
        result = _detect_id_lookup("SELECT * FROM stripe.customers WHERE id = 'cus_1';")
        assert result == ("stripe", "customers", "cus_1")

    def test_rejects_join(self):
        sql = "SELECT * FROM stripe.customers s JOIN hubspot.contacts h ON s.email = h.email WHERE s.id = '123'"
        assert _detect_id_lookup(sql) is None

    def test_rejects_and(self):
        sql = "SELECT * FROM stripe.customers WHERE id = '123' AND name = 'Alice'"
        assert _detect_id_lookup(sql) is None

    def test_rejects_or(self):
        sql = "SELECT * FROM stripe.customers WHERE id = '123' OR id = '456'"
        assert _detect_id_lookup(sql) is None

    def test_rejects_non_pk_column(self):
        sql = "SELECT * FROM stripe.customers WHERE email = 'test@example.com'"
        assert _detect_id_lookup(sql) is None

    def test_rejects_update(self):
        sql = "UPDATE stripe.customers SET name = 'x' WHERE id = '123'"
        assert _detect_id_lookup(sql) is None

    def test_rejects_no_schema(self):
        sql = "SELECT * FROM customers WHERE id = '123'"
        assert _detect_id_lookup(sql) is None

    def test_pk_column(self):
        result = _detect_id_lookup("SELECT * FROM stripe.customers WHERE pk = '123'")
        assert result == ("stripe", "customers", "123")

    def test_uuid_column(self):
        result = _detect_id_lookup("SELECT * FROM stripe.customers WHERE uuid = 'abc-def'")
        assert result == ("stripe", "customers", "abc-def")

    def test_case_insensitive(self):
        result = _detect_id_lookup("select * from Stripe.Customers where ID = '123'")
        assert result == ("Stripe", "Customers", "123")


# ---------------------------------------------------------------------------
# LiveFetchClient
# ---------------------------------------------------------------------------

class TestLiveFetchClient:
    def test_available_with_config(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("intercom", {"token": "fake"})
        assert client.available is True

    def test_not_available_without_config(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("nonexistent_source_xyz", {})
        assert client.available is False

    def test_can_fetch_known_table(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("intercom", {"token": "fake"})
        assert client.can_fetch("contacts") is True

    def test_cannot_fetch_unknown_table(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("intercom", {"token": "fake"})
        assert client.can_fetch("nonexistent_table") is False

    def test_fetch_by_id_returns_none_on_no_config(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("nonexistent_source_xyz", {})
        assert client.fetch_by_id("contacts", "123") is None

    # --- Verified source fallback tests ---

    def test_available_with_verified_source_hubspot(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("hubspot", {"api_key": "fake"})
        assert client.available is True

    def test_available_with_verified_source_stripe(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("stripe", {"stripe_secret_key": "fake"})
        assert client.available is True

    def test_can_fetch_hubspot_contacts(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("hubspot", {"api_key": "fake"})
        assert client.can_fetch("contacts") is True
        assert client.can_fetch("deals") is True
        assert client.can_fetch("nonexistent_table") is False

    def test_can_fetch_stripe_customers(self):
        from dinobase.fetch.client import LiveFetchClient
        client = LiveFetchClient("stripe", {"stripe_secret_key": "fake"})
        assert client.can_fetch("customers") is True
        assert client.can_fetch("charges") is True

    def test_verified_source_builds_correct_url(self):
        """Verify that the URL is constructed correctly from live_fetch_config."""
        from dinobase.fetch.client import LiveFetchClient
        from dinobase.sync.source_config import get_resource, get_client_base_url
        client = LiveFetchClient("hubspot", {"api_key": "fake"})
        base_url = get_client_base_url(client.config, client.credentials)
        resource = get_resource(client.config, "contacts")
        path = resource["endpoint"]["path"]
        url = f"{base_url}/{path.strip('/')}/123"
        assert url == "https://api.hubapi.com/crm/v3/objects/contacts/123"

    def test_verified_source_builds_correct_auth(self):
        """Verify that auth headers are built correctly from live_fetch_config."""
        from dinobase.fetch.client import LiveFetchClient
        from dinobase.sync.source_config import build_client_auth_headers
        client = LiveFetchClient("stripe", {"stripe_secret_key": "sk_test_123"})
        headers = build_client_auth_headers(client.config, client.credentials)
        assert headers == {"Authorization": "Bearer sk_test_123"}


# ---------------------------------------------------------------------------
# source_config helpers
# ---------------------------------------------------------------------------

class TestSourceConfigHelpers:
    def test_build_client_auth_headers_bearer(self):
        from dinobase.sync.source_config import build_client_auth_headers
        config = {"client": {"auth": {"type": "bearer", "token": "{token}"}}}
        headers = build_client_auth_headers(config, {"token": "my_secret"})
        assert headers == {"Authorization": "Bearer my_secret"}

    def test_build_client_auth_headers_basic(self):
        from dinobase.sync.source_config import build_client_auth_headers
        import base64
        config = {"client": {"auth": {"type": "http_basic", "username": "{api_key}", "password": ""}}}
        headers = build_client_auth_headers(config, {"api_key": "test_key"})
        expected = base64.b64encode(b"test_key:").decode()
        assert headers == {"Authorization": f"Basic {expected}"}

    def test_get_client_base_url_with_substitution(self):
        from dinobase.sync.source_config import get_client_base_url
        config = {"client": {"base_url": "https://{site}.chargebee.com/api/v2/"}}
        url = get_client_base_url(config, {"site": "acme"})
        assert url == "https://acme.chargebee.com/api/v2"

    def test_get_resource(self):
        from dinobase.sync.source_config import get_resource
        config = {"resources": [
            {"name": "contacts", "endpoint": {"path": "contacts"}},
            {"name": "companies", "endpoint": {"path": "companies"}},
        ]}
        r = get_resource(config, "contacts")
        assert r is not None
        assert r["name"] == "contacts"

    def test_get_resource_not_found(self):
        from dinobase.sync.source_config import get_resource
        config = {"resources": [{"name": "contacts", "endpoint": {"path": "contacts"}}]}
        assert get_resource(config, "xyz") is None

    def test_get_resource_primary_key_default(self):
        from dinobase.sync.source_config import get_resource_primary_key
        config = {"resource_defaults": {"primary_key": "id"}}
        resource = {"name": "contacts"}
        assert get_resource_primary_key(config, resource) == "id"

    def test_get_resource_primary_key_override(self):
        from dinobase.sync.source_config import get_resource_primary_key
        config = {"resource_defaults": {"primary_key": "id"}}
        resource = {"name": "events", "primary_key": "event_id"}
        assert get_resource_primary_key(config, resource) == "event_id"

    def test_get_client_headers(self):
        from dinobase.sync.source_config import get_client_headers
        config = {"client": {"headers": {"Intercom-Version": "2.10"}}}
        headers = get_client_headers(config, {})
        assert headers == {"Intercom-Version": "2.10"}


# ---------------------------------------------------------------------------
# Integration: execute() with live fetch
# ---------------------------------------------------------------------------

class TestExecuteLiveFetch:
    def test_fresh_source_queries_parquet(self, sample_db):
        """Fresh source should NOT trigger live fetch."""
        engine = QueryEngine(sample_db)
        result = engine.execute("SELECT * FROM stripe.customers WHERE id = 'cus_001'")
        # Should use parquet (synced), not live
        assert result.get("_freshness") == "synced"

    def test_stale_source_without_config_falls_back(self, sample_db):
        """Stale source without YAML config should fall back to parquet."""
        # Backdate sync to make stripe stale
        old_time = datetime.now(timezone.utc) - timedelta(hours=3)
        sample_db.conn.execute(
            "UPDATE _dinobase.sync_log SET finished_at = ? WHERE source_name = 'stripe'",
            [old_time],
        )

        engine = QueryEngine(sample_db)
        # stripe doesn't have a YAML config in sources/configs/ (it uses dlt verified source)
        result = engine.execute("SELECT * FROM stripe.customers WHERE id = 'cus_001'")
        # Should fall back to parquet
        assert result.get("_freshness") == "synced"

    def test_complex_query_skips_live_fetch(self, sample_db):
        """JOINs and multi-condition queries should never trigger live fetch."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=3)
        sample_db.conn.execute(
            "UPDATE _dinobase.sync_log SET finished_at = ? WHERE source_name = 'stripe'",
            [old_time],
        )

        engine = QueryEngine(sample_db)
        result = engine.execute(
            "SELECT s.*, h.company FROM stripe.customers s "
            "JOIN hubspot.contacts h ON s.email = h.email LIMIT 5"
        )
        assert result.get("_freshness") == "synced"
        assert "error" not in result
