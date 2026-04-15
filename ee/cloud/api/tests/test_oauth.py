# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).

"""Tests for the OAuth router (migrated from ee/oauth-proxy/)."""

from __future__ import annotations

import os
from unittest.mock import patch, AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient, ASGITransport, Response

from dinobase_hosted.app import app
from dinobase_hosted.oauth.providers import PROVIDERS


TEST_BASE_URL = "https://proxy.test"
TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def env_base():
    """Set the public base URL and encryption key used by state sealing."""
    env = {
        "DINOBASE_BASE_URL": TEST_BASE_URL,
        "DINOBASE_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY,
    }
    with patch.dict(os.environ, env):
        yield


@pytest.fixture
def env_creds():
    """Set up HubSpot client credentials in env."""
    env = {
        "DINOBASE_OAUTH_HUBSPOT_CLIENT_ID": "test_client_id",
        "DINOBASE_OAUTH_HUBSPOT_CLIENT_SECRET": "test_client_secret",
    }
    with patch.dict(os.environ, env):
        yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /oauth/providers
# ---------------------------------------------------------------------------

async def test_list_providers(client):
    resp = await client.get("/oauth/providers")
    assert resp.status_code == 200
    providers = resp.json()
    names = [p["name"] for p in providers]
    assert "hubspot" in names
    assert "github" in names
    assert "salesforce" in names


async def test_providers_show_configured_status(client, env_creds):
    resp = await client.get("/oauth/providers")
    providers = {p["name"]: p for p in resp.json()}
    assert providers["hubspot"]["configured"] is True
    assert providers["github"]["configured"] is False


# ---------------------------------------------------------------------------
# GET /oauth/auth/{provider}
# ---------------------------------------------------------------------------

async def test_auth_redirects_to_provider(client, env_creds):
    resp = await client.get(
        "/oauth/auth/hubspot",
        params={"redirect_uri": "http://localhost:9999/callback", "state": "abc123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "app.hubspot.com/oauth/authorize" in location

    parsed = urlparse(location)
    q = parse_qs(parsed.query)
    assert q["client_id"] == ["test_client_id"]
    # Provider sees the proxy's own callback, not the client's local URL.
    assert q["redirect_uri"] == [f"{TEST_BASE_URL}/oauth/callback/hubspot"]
    # The state sent to the provider is sealed, not the client's raw state.
    assert q["state"] != ["abc123"]
    assert len(q["state"][0]) > 20


async def test_auth_rejects_non_localhost_http_redirect(client, env_creds):
    resp = await client.get(
        "/oauth/auth/hubspot",
        params={"redirect_uri": "http://evil.example/cb", "state": "x"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


async def test_auth_unknown_provider(client):
    resp = await client.get(
        "/oauth/auth/nonexistent",
        params={"redirect_uri": "http://localhost:9999/callback", "state": "x"},
    )
    assert resp.status_code == 404


async def test_auth_unconfigured_provider(client):
    resp = await client.get(
        "/oauth/auth/github",
        params={"redirect_uri": "http://localhost:9999/callback", "state": "x"},
    )
    assert resp.status_code == 501
    assert "not configured" in resp.json()["detail"]


async def test_auth_includes_scopes(client, env_creds):
    resp = await client.get(
        "/oauth/auth/hubspot",
        params={"redirect_uri": "http://localhost:9999/callback", "state": "s"},
        follow_redirects=False,
    )
    location = resp.headers["location"]
    assert "scope=" in location
    assert "crm.objects.contacts.read" in location


# ---------------------------------------------------------------------------
# GET /oauth/callback/{provider}
# ---------------------------------------------------------------------------

async def _sealed_state(client, provider: str, redirect_uri: str, state: str) -> str:
    """Drive /auth to obtain a sealed state token, then return it."""
    resp = await client.get(
        f"/oauth/auth/{provider}",
        params={"redirect_uri": redirect_uri, "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return parse_qs(urlparse(resp.headers["location"]).query)["state"][0]


async def test_callback_forwards_code_to_client(client, env_creds):
    sealed = await _sealed_state(
        client, "hubspot", "http://localhost:9999/callback", "client_state"
    )

    resp = await client.get(
        "/oauth/callback/hubspot",
        params={"code": "the_code", "state": sealed},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    loc = urlparse(resp.headers["location"])
    assert loc.hostname == "localhost"
    assert loc.port == 9999
    assert loc.path == "/callback"
    q = parse_qs(loc.query)
    assert q["code"] == ["the_code"]
    assert q["state"] == ["client_state"]


async def test_callback_forwards_error_to_client(client, env_creds):
    sealed = await _sealed_state(
        client, "hubspot", "http://localhost:9999/callback", "cs"
    )

    resp = await client.get(
        "/oauth/callback/hubspot",
        params={"error": "access_denied", "error_description": "user said no", "state": sealed},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert q["error"] == ["access_denied"]
    assert q["error_description"] == ["user said no"]
    assert q["state"] == ["cs"]
    assert "code" not in q


async def test_callback_rejects_tampered_state(client, env_creds):
    resp = await client.get(
        "/oauth/callback/hubspot",
        params={"code": "c", "state": "not-a-real-sealed-token"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


async def test_callback_forwards_ctx_param(client, env_creds):
    """The ctx param round-trips the sealed state blob back to the client."""
    sealed = await _sealed_state(
        client, "hubspot", "http://localhost:9999/callback", "cs"
    )
    resp = await client.get(
        "/oauth/callback/hubspot",
        params={"code": "c", "state": sealed},
        follow_redirects=False,
    )
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert q["ctx"] == [sealed]


async def test_callback_rejects_cross_provider_state(client, env_creds):
    """A state sealed for provider A must not be usable at provider B's callback."""
    sealed = await _sealed_state(
        client, "hubspot", "http://localhost:9999/callback", "cs"
    )
    # linear isn't configured, so it'd normally 501 — but the state check
    # runs before credentials lookup. Use hubspot_marketing which is also
    # unconfigured but passes the provider-name lookup.
    resp = await client.get(
        "/oauth/callback/hubspot_marketing",
        params={"code": "c", "state": sealed},
        follow_redirects=False,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /oauth/token/{provider}
# ---------------------------------------------------------------------------

async def test_token_exchange(client, env_creds):
    mock_resp = Response(
        200,
        json={
            "access_token": "at_new",
            "refresh_token": "rt_new",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )

    with patch("dinobase_hosted.oauth.router.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/oauth/token/hubspot",
            json={"code": "auth_code_123", "redirect_uri": "http://localhost:9999/callback"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "at_new"
    assert data["refresh_token"] == "rt_new"
    assert data["expires_in"] == 3600

    # The proxy must send its own callback URL to the provider, not the
    # client's ephemeral localhost URL — otherwise the provider would reject
    # the exchange due to redirect_uri mismatch with the /auth step.
    sent_data = mock_instance.post.call_args.kwargs["data"]
    assert sent_data["redirect_uri"] == f"{TEST_BASE_URL}/oauth/callback/hubspot"
    assert sent_data["code"] == "auth_code_123"


async def test_token_exchange_provider_error(client, env_creds):
    mock_resp = Response(400, text="invalid_grant")

    with patch("dinobase_hosted.oauth.router.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/oauth/token/hubspot",
            json={"code": "bad_code", "redirect_uri": "http://localhost:9999/callback"},
        )

    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /oauth/refresh/{provider}
# ---------------------------------------------------------------------------

async def test_refresh_token(client, env_creds):
    mock_resp = Response(
        200,
        json={
            "access_token": "at_refreshed",
            "expires_in": 7200,
            "token_type": "Bearer",
        },
    )

    with patch("dinobase_hosted.oauth.router.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/oauth/refresh/hubspot",
            json={"refresh_token": "rt_old"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "at_refreshed"
    assert data["expires_in"] == 7200


async def test_refresh_with_rotated_token(client, env_creds):
    mock_resp = Response(
        200,
        json={
            "access_token": "at_new",
            "refresh_token": "rt_rotated",
            "expires_in": 3600,
        },
    )

    with patch("dinobase_hosted.oauth.router.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/oauth/refresh/hubspot",
            json={"refresh_token": "rt_old"},
        )

    data = resp.json()
    assert data["refresh_token"] == "rt_rotated"


# ---------------------------------------------------------------------------
# Health + Provider registry
# ---------------------------------------------------------------------------

async def test_health(client):
    resp = await client.get("/oauth/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_provider_count():
    assert len(PROVIDERS) >= 30


def test_all_providers_have_urls():
    for name, p in PROVIDERS.items():
        assert p.authorization_url, f"{name} missing authorization_url"
        assert p.token_url, f"{name} missing token_url"


def test_trello_removed():
    """Trello uses OAuth 1.0a and is incompatible with this proxy."""
    assert "trello" not in PROVIDERS


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------


@pytest.fixture
def env_airtable_creds():
    env = {
        "DINOBASE_OAUTH_AIRTABLE_CLIENT_ID": "at_client_id",
        "DINOBASE_OAUTH_AIRTABLE_CLIENT_SECRET": "at_client_secret",
    }
    with patch.dict(os.environ, env):
        yield


async def test_auth_includes_pkce_for_airtable(client, env_airtable_creds):
    resp = await client.get(
        "/oauth/auth/airtable",
        params={"redirect_uri": "http://localhost:9999/callback", "state": "cs"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"]
    assert len(q["code_challenge"][0]) >= 43  # base64url(sha256) = 43 chars


async def test_auth_omits_pkce_for_non_pkce_providers(client, env_creds):
    resp = await client.get(
        "/oauth/auth/hubspot",
        params={"redirect_uri": "http://localhost:9999/callback", "state": "cs"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert "code_challenge" not in q
    assert "code_challenge_method" not in q


async def _full_flow_ctx(client, provider: str, subdomain: str | None = None) -> tuple[str, str]:
    """Drive /auth then /callback and return (code, ctx) as the client would see them."""
    params = {"redirect_uri": "http://localhost:9999/callback", "state": "cs"}
    if subdomain:
        params["subdomain"] = subdomain
    auth_resp = await client.get(
        f"/oauth/auth/{provider}", params=params, follow_redirects=False,
    )
    sealed = parse_qs(urlparse(auth_resp.headers["location"]).query)["state"][0]

    cb_resp = await client.get(
        f"/oauth/callback/{provider}",
        params={"code": "the_code", "state": sealed},
        follow_redirects=False,
    )
    cb_q = parse_qs(urlparse(cb_resp.headers["location"]).query)
    return cb_q["code"][0], cb_q["ctx"][0]


async def test_token_exchange_sends_code_verifier_for_pkce(client, env_airtable_creds):
    code, ctx = await _full_flow_ctx(client, "airtable")

    mock_resp = Response(200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    with patch("dinobase_hosted.oauth.router.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/oauth/token/airtable",
            json={"code": code, "ctx": ctx},
        )

    assert resp.status_code == 200
    sent = mock_instance.post.call_args.kwargs["data"]
    assert "code_verifier" in sent
    assert len(sent["code_verifier"]) >= 43
    # Verifier must NOT leak in cleartext anywhere the client could see it.
    assert sent["code_verifier"] not in ctx


async def test_token_exchange_rejects_pkce_without_ctx(client, env_airtable_creds):
    resp = await client.post(
        "/oauth/token/airtable",
        json={"code": "some_code"},
    )
    assert resp.status_code == 400
    assert "PKCE" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tenant subdomain (Shopify, Zendesk, WooCommerce)
# ---------------------------------------------------------------------------


@pytest.fixture
def env_shopify_creds():
    env = {
        "DINOBASE_OAUTH_SHOPIFY_CLIENT_ID": "sh_id",
        "DINOBASE_OAUTH_SHOPIFY_CLIENT_SECRET": "sh_secret",
    }
    with patch.dict(os.environ, env):
        yield


async def test_auth_substitutes_shop_subdomain(client, env_shopify_creds):
    resp = await client.get(
        "/oauth/auth/shopify",
        params={
            "redirect_uri": "http://localhost:9999/callback",
            "state": "cs",
            "subdomain": "acmestore",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "acmestore.myshopify.com/admin/oauth/authorize" in location
    assert "{shop}" not in location


async def test_auth_rejects_missing_subdomain(client, env_shopify_creds):
    resp = await client.get(
        "/oauth/auth/shopify",
        params={"redirect_uri": "http://localhost:9999/callback", "state": "cs"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


async def test_auth_rejects_malicious_subdomain(client, env_shopify_creds):
    resp = await client.get(
        "/oauth/auth/shopify",
        params={
            "redirect_uri": "http://localhost:9999/callback",
            "state": "cs",
            "subdomain": "evil/../escape",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400


async def test_token_exchange_substitutes_subdomain(client, env_shopify_creds):
    code, ctx = await _full_flow_ctx(client, "shopify", subdomain="acmestore")

    mock_resp = Response(200, json={"access_token": "at"})
    with patch("dinobase_hosted.oauth.router.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/oauth/token/shopify",
            json={"code": code, "ctx": ctx},
        )

    assert resp.status_code == 200
    # The proxy must have hit the tenant-specific token URL.
    called_url = mock_instance.post.call_args.args[0]
    assert "acmestore.myshopify.com" in called_url
    assert "{shop}" not in called_url
