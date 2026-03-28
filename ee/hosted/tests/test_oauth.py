# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).

"""Tests for the OAuth router (migrated from ee/oauth-proxy/)."""

from __future__ import annotations

import os
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport, Response

from dinobase_hosted.app import app
from dinobase_hosted.oauth.providers import PROVIDERS


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
    assert "client_id=test_client_id" in location
    assert "state=abc123" in location


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
