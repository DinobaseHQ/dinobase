"""OAuth flow for Dinobase — handles browser-based auth and token refresh via a proxy."""

from __future__ import annotations

import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import URLError

import json


DEFAULT_PROXY_URL = "https://auth.dinobase.dev"
TOKEN_EXPIRY_BUFFER_SECONDS = 300  # refresh 5 min before expiry


def get_proxy_url() -> str:
    """Get the OAuth proxy URL from env or config."""
    url = os.environ.get("DINOBASE_OAUTH_PROXY_URL")
    if url:
        return url.rstrip("/")

    from dinobase.config import load_config
    config = load_config()
    return config.get("oauth_proxy_url", DEFAULT_PROXY_URL).rstrip("/")


# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth callback redirect from the proxy."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        error = params.get("error", [None])[0]
        if error:
            self.server.oauth_result = {"error": error, "error_description": params.get("error_description", [""])[0]}  # type: ignore[attr-defined]
        else:
            # Capture all query params — supports both OAuth code flow
            # and direct token passing from the web frontend
            self.server.oauth_result = {  # type: ignore[attr-defined]
                k: v[0] for k, v in params.items()
            }

        # Show a nice page and close the tab
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        body = (
            "<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
            "<h2>Connected!</h2>"
            "<p>You can close this tab and return to the terminal.</p>"
            "<script>window.close()</script>"
            "</body></html>"
        )
        self.wfile.write(body.encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass  # silence request logs


def _start_callback_server() -> HTTPServer:
    """Start a local HTTP server on a random port to receive the OAuth callback."""
    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.oauth_result = None  # type: ignore[attr-defined]
    server.timeout = 120
    return server


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

def _proxy_request(url: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make a JSON request to the OAuth proxy."""
    if data is not None:
        req = Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    else:
        req = Request(url)

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except URLError as e:
        raise RuntimeError(f"Failed to reach OAuth proxy at {url}: {e}") from e


def _exchange_code(provider: str, code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens via the proxy."""
    proxy_url = get_proxy_url()
    return _proxy_request(
        f"{proxy_url}/token/{provider}",
        {"code": code, "redirect_uri": redirect_uri},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def authorize(provider: str) -> dict[str, str]:
    """Run the full OAuth authorization flow for a provider.

    1. Starts a local callback server
    2. Opens the browser to the proxy's auth URL
    3. Waits for the callback with an auth code
    4. Exchanges the code for tokens
    5. Returns credentials dict ready for config storage

    Returns:
        dict with access_token, refresh_token, expires_at, auth_method="oauth"
    """
    server = _start_callback_server()
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(32)

    proxy_url = get_proxy_url()
    auth_url = f"{proxy_url}/auth/{provider}?" + urlencode({
        "redirect_uri": redirect_uri,
        "state": state,
    })

    print(f"Opening browser to authorize {provider}...", file=sys.stderr)
    print(f"If the browser doesn't open, visit:\n  {auth_url}\n", file=sys.stderr)
    webbrowser.open(auth_url)

    # Wait for callback
    while server.oauth_result is None:  # type: ignore[attr-defined]
        server.handle_request()

    server.server_close()

    result = server.oauth_result  # type: ignore[attr-defined]

    if "error" in result:
        raise RuntimeError(
            f"OAuth authorization failed: {result['error']} — {result.get('error_description', '')}"
        )

    if result.get("state") != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF attack")

    code = result["code"]
    if not code:
        raise RuntimeError("No authorization code received from OAuth callback")

    # Exchange code for tokens
    tokens = _exchange_code(provider, code, redirect_uri)

    expires_at = ""
    if "expires_in" in tokens:
        expires_at = str(int(time.time()) + int(tokens["expires_in"]))

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": expires_at,
        "auth_method": "oauth",
    }


def refresh_access_token(provider: str, refresh_token: str) -> dict[str, Any]:
    """Refresh an access token via the proxy.

    Returns the proxy response with at least: access_token, expires_in.
    May also include a rotated refresh_token.
    """
    proxy_url = get_proxy_url()
    return _proxy_request(
        f"{proxy_url}/refresh/{provider}",
        {"refresh_token": refresh_token},
    )


def ensure_fresh_credentials(
    source_name: str,
    source_type: str,
    credentials: dict[str, str],
) -> dict[str, str]:
    """Check if OAuth credentials are expired and refresh if needed.

    For non-OAuth sources (no auth_method=oauth), returns credentials unchanged.
    For OAuth sources with valid tokens, returns credentials unchanged.
    For OAuth sources with expired tokens, refreshes and updates config.

    Returns:
        Credentials dict with a fresh access_token.
    """
    if credentials.get("auth_method") != "oauth":
        return credentials

    expires_at = credentials.get("expires_at", "")
    if not expires_at:
        return credentials  # no expiry info, use as-is

    try:
        expiry = int(expires_at)
    except ValueError:
        return credentials

    if time.time() < expiry - TOKEN_EXPIRY_BUFFER_SECONDS:
        return credentials  # still valid

    # Token is expired or about to expire — refresh it
    rt = credentials.get("refresh_token", "")
    if not rt:
        raise RuntimeError(
            f"OAuth token for '{source_name}' has expired and no refresh token "
            f"is available. Run `dinobase auth {source_type}` to re-authorize."
        )

    print(f"Refreshing OAuth token for {source_name}...", file=sys.stderr)
    tokens = refresh_access_token(source_type, rt)

    # Update credentials
    credentials["access_token"] = tokens["access_token"]
    if "refresh_token" in tokens:
        credentials["refresh_token"] = tokens["refresh_token"]
    if "expires_in" in tokens:
        credentials["expires_at"] = str(int(time.time()) + int(tokens["expires_in"]))

    # Persist updated tokens to config
    from dinobase.config import update_credentials
    update_credentials(source_name, credentials)

    return credentials


def list_providers() -> list[dict[str, Any]]:
    """Fetch the list of OAuth-supported providers from the proxy."""
    proxy_url = get_proxy_url()
    return _proxy_request(f"{proxy_url}/providers")  # type: ignore[return-value]
