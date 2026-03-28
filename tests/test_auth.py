"""Tests for the OAuth auth module."""

import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from unittest.mock import patch, MagicMock

import pytest
import yaml
from click.testing import CliRunner

from dinobase.auth import (
    authorize,
    ensure_fresh_credentials,
    refresh_access_token,
    get_proxy_url,
    DEFAULT_PROXY_URL,
    TOKEN_EXPIRY_BUFFER_SECONDS,
)
from dinobase.cli import cli


@pytest.fixture
def runner(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    yield CliRunner()
    os.environ.pop("DINOBASE_DIR", None)


@pytest.fixture
def tmp_config(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({"sources": {}}))
    yield tmp_path
    os.environ.pop("DINOBASE_DIR", None)


# ---------------------------------------------------------------------------
# get_proxy_url
# ---------------------------------------------------------------------------

def test_proxy_url_default():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("DINOBASE_OAUTH_PROXY_URL", None)
        with patch("dinobase.config.load_config", return_value={"sources": {}}):
            assert get_proxy_url() == DEFAULT_PROXY_URL


def test_proxy_url_from_env():
    with patch.dict(os.environ, {"DINOBASE_OAUTH_PROXY_URL": "https://custom.proxy"}):
        assert get_proxy_url() == "https://custom.proxy"


def test_proxy_url_from_config():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("DINOBASE_OAUTH_PROXY_URL", None)
        cfg = {"sources": {}, "oauth_proxy_url": "https://config.proxy"}
        with patch("dinobase.config.load_config", return_value=cfg):
            assert get_proxy_url() == "https://config.proxy"


def test_proxy_url_strips_trailing_slash():
    with patch.dict(os.environ, {"DINOBASE_OAUTH_PROXY_URL": "https://proxy.dev/"}):
        assert get_proxy_url() == "https://proxy.dev"


# ---------------------------------------------------------------------------
# ensure_fresh_credentials
# ---------------------------------------------------------------------------

def test_non_oauth_credentials_returned_unchanged():
    creds = {"api_key": "sk_test_123"}
    result = ensure_fresh_credentials("stripe", "stripe", creds)
    assert result is creds


def test_oauth_credentials_not_expired(tmp_config):
    future = str(int(time.time()) + 3600)
    creds = {
        "access_token": "valid_token",
        "refresh_token": "rt_123",
        "expires_at": future,
        "auth_method": "oauth",
    }
    result = ensure_fresh_credentials("hubspot", "hubspot", creds)
    assert result["access_token"] == "valid_token"


def test_oauth_credentials_expired_refreshes(tmp_config):
    past = str(int(time.time()) - 100)
    creds = {
        "access_token": "old_token",
        "refresh_token": "rt_123",
        "expires_at": past,
        "auth_method": "oauth",
    }

    # Set up source in config so update_credentials can find it
    from dinobase.config import add_source
    add_source("hubspot", "hubspot", creds)

    mock_response = {
        "access_token": "new_token",
        "refresh_token": "rt_456",
        "expires_in": 3600,
    }
    with patch("dinobase.auth.refresh_access_token", return_value=mock_response):
        result = ensure_fresh_credentials("hubspot", "hubspot", creds)

    assert result["access_token"] == "new_token"
    assert result["refresh_token"] == "rt_456"
    assert int(result["expires_at"]) > int(time.time())


def test_oauth_expired_no_refresh_token_raises(tmp_config):
    past = str(int(time.time()) - 100)
    creds = {
        "access_token": "old_token",
        "refresh_token": "",
        "expires_at": past,
        "auth_method": "oauth",
    }

    with pytest.raises(RuntimeError, match="no refresh token"):
        ensure_fresh_credentials("hubspot", "hubspot", creds)


def test_oauth_within_buffer_still_refreshes(tmp_config):
    """Token that expires within the buffer window should be refreshed."""
    almost_expired = str(int(time.time()) + TOKEN_EXPIRY_BUFFER_SECONDS - 10)
    creds = {
        "access_token": "almost_expired_token",
        "refresh_token": "rt_123",
        "expires_at": almost_expired,
        "auth_method": "oauth",
    }

    from dinobase.config import add_source
    add_source("hubspot", "hubspot", creds)

    mock_response = {"access_token": "new_token", "expires_in": 3600}
    with patch("dinobase.auth.refresh_access_token", return_value=mock_response):
        result = ensure_fresh_credentials("hubspot", "hubspot", creds)

    assert result["access_token"] == "new_token"


def test_oauth_no_expiry_returns_unchanged():
    creds = {
        "access_token": "token_no_expiry",
        "auth_method": "oauth",
    }
    result = ensure_fresh_credentials("test", "test", creds)
    assert result["access_token"] == "token_no_expiry"


# ---------------------------------------------------------------------------
# CLI: dinobase auth
# ---------------------------------------------------------------------------

def test_auth_unknown_source(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["auth", "nonexistent_source_xyz"])
    assert result.exit_code != 0
    assert "Unknown source" in result.output


def test_auth_requires_cloud_login(runner):
    """Auth should fail with a cloud login prompt when not logged in."""
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["auth", "hubspot"])
    assert result.exit_code != 0
    assert "Cloud account required" in result.output


def test_auth_headless_requires_cloud_login(runner):
    """Headless auth should return JSON error when not logged in."""
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["auth", "hubspot", "--headless"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert data["status"] == "error"
    assert "Cloud account required" in data["error"]


def test_auth_with_cloud_starts_oauth(runner):
    """When logged in to cloud, auth should start the OAuth flow."""
    runner.invoke(cli, ["init"])

    mock_client = MagicMock()
    mock_client.start_oauth.return_value = {
        "auth_url": "https://auth.dinobase.dev/oauth/auth/hubspot?...",
        "state": "test_state",
    }
    mock_client.complete_oauth.return_value = {
        "name": "hubspot",
        "type": "hubspot",
        "status": "connected",
    }

    # Mock a callback server that immediately returns a code
    mock_server = MagicMock()
    mock_server.server_address = ("127.0.0.1", 12345)
    mock_server.oauth_result = {"code": "test_code", "state": "test_state"}

    with (
        patch("dinobase.config.is_cloud_logged_in", return_value=True),
        patch("dinobase.cli._get_cloud_client", return_value=mock_client),
        patch("dinobase.cli._start_callback_server", create=True, return_value=mock_server),
    ):
        # Patch the import inside the auth function
        import dinobase.auth
        original = dinobase.auth._start_callback_server
        dinobase.auth._start_callback_server = lambda: mock_server
        try:
            result = runner.invoke(cli, ["auth", "hubspot", "--headless"])
        finally:
            dinobase.auth._start_callback_server = original

    assert result.exit_code == 0
    # Should have printed the auth URL and then the connected status
    lines = [l for l in result.output.strip().split("\n") if l.strip()]
    assert any("auth_url" in l for l in lines)
    assert any("connected" in l for l in lines)


# ---------------------------------------------------------------------------
# Token refresh persists to config
# ---------------------------------------------------------------------------

def test_refresh_updates_config_file(tmp_config):
    past = str(int(time.time()) - 100)
    creds = {
        "access_token": "old",
        "refresh_token": "rt_123",
        "expires_at": past,
        "auth_method": "oauth",
    }

    from dinobase.config import add_source
    add_source("test_source", "hubspot", creds)

    mock_response = {
        "access_token": "refreshed",
        "refresh_token": "rt_new",
        "expires_in": 7200,
    }
    with patch("dinobase.auth.refresh_access_token", return_value=mock_response):
        ensure_fresh_credentials("test_source", "hubspot", creds)

    # Verify config was updated on disk
    with open(tmp_config / "config.yaml") as f:
        config = yaml.safe_load(f)

    assert config["sources"]["test_source"]["credentials"]["access_token"] == "refreshed"
    assert config["sources"]["test_source"]["credentials"]["refresh_token"] == "rt_new"


# ---------------------------------------------------------------------------
# Registry: supports_oauth flag
# ---------------------------------------------------------------------------

def test_registry_oauth_flag():
    from dinobase.sync.registry import get_source_entry

    hubspot = get_source_entry("hubspot")
    assert hubspot is not None
    assert hubspot.supports_oauth is True

    stripe = get_source_entry("stripe")
    assert stripe is not None
    assert stripe.supports_oauth is False


def test_yaml_source_oauth_flag():
    from dinobase.sync.registry import get_source_entry

    hubspot_marketing = get_source_entry("hubspot_marketing")
    assert hubspot_marketing is not None
    assert hubspot_marketing.supports_oauth is True

    # A source without oauth: true
    posthog = get_source_entry("posthog")
    assert posthog is not None
    assert posthog.supports_oauth is False
