"""HTTP server for `dinobase setup` — bundled localhost config GUI."""

from __future__ import annotations

import json
import secrets
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from dinobase import __version__
from dinobase.setup_server import routes as _routes
from dinobase.setup_server.ui_bundle import UIBundle
from dinobase.setup_server.ui_manifest import resolve_ui_bundle


OAUTH_STATE_TTL_SECONDS = 600
# On `pagehide` the browser can't tell "real close" from "reload", so the UI
# always sends a quit signal on unload. We delay the actual shutdown by a
# short grace period and cancel it if a new request arrives (a reload will
# re-fetch `/` within milliseconds).
QUIT_GRACE_SECONDS = 2.0


class SetupServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying setup-GUI state.

    State is accessed from request-handler threads, so all mutations go
    through ``self._lock``.
    """

    def __init__(self, address: tuple[str, int], handler_cls: type, ui_bundle: UIBundle) -> None:
        super().__init__(address, handler_cls)
        self.local_token: str = secrets.token_urlsafe(32)
        self.pending_oauth: dict[str, dict[str, Any]] = {}
        self.pending_cloud_login: dict[str, dict[str, Any]] = {}
        self.quit_event = threading.Event()
        self.quit_scheduled_at: float | None = None
        self._lock = threading.Lock()
        self.ui_bundle: UIBundle = ui_bundle

    # ---- Quit scheduling ----

    def schedule_quit(self) -> None:
        with self._lock:
            self.quit_scheduled_at = time.time()

    def cancel_quit(self) -> None:
        with self._lock:
            self.quit_scheduled_at = None

    # ---- OAuth state tracking ----

    def remember_oauth(self, state: str, payload: dict[str, Any]) -> None:
        payload = {**payload, "started_at": time.time()}
        with self._lock:
            self._evict_expired()
            self.pending_oauth[state] = payload

    def pop_oauth(self, state: str) -> dict[str, Any] | None:
        with self._lock:
            self._evict_expired()
            return self.pending_oauth.pop(state, None)

    def remember_cloud_login(self, state: str, payload: dict[str, Any]) -> None:
        payload = {**payload, "started_at": time.time()}
        with self._lock:
            self._evict_expired()
            self.pending_cloud_login[state] = payload

    def pop_cloud_login(self, state: str) -> dict[str, Any] | None:
        with self._lock:
            self._evict_expired()
            return self.pending_cloud_login.pop(state, None)

    def _evict_expired(self) -> None:
        cutoff = time.time() - OAUTH_STATE_TTL_SECONDS
        for bucket in (self.pending_oauth, self.pending_cloud_login):
            stale = [k for k, v in bucket.items() if v.get("started_at", 0) < cutoff]
            for k in stale:
                bucket.pop(k, None)


class SetupHandler(BaseHTTPRequestHandler):
    """Dispatch to routes + static assets, enforce Host/token checks."""

    server_version = "DinobaseSetup/1.0"

    # Silence default access logging
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    # ---- helpers ----

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "")
        expected_port = self.server.server_address[1]
        return host in (
            f"127.0.0.1:{expected_port}",
            f"localhost:{expected_port}",
        )

    def _has_token(self) -> bool:
        sent = self.headers.get("X-Dinobase-Local-Token", "")
        return secrets.compare_digest(sent, self.server.local_token)

    def _send_json(self, status: int, body: Any) -> None:
        payload = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self._send_bytes(status, body.encode(), content_type)

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return None
        raw = self.rfile.read(length)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    # ---- dispatch ----

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # Host check applies to everything.
        if not self._valid_host():
            self._send_text(400, "Bad Host header")
            return

        # Any incoming request (other than the quit signal itself) cancels
        # a pending shutdown — a page reload fires pagehide + new GET /,
        # so the new GET lands here and keeps the server alive.
        if path != "/api/local/quit":
            self.server.cancel_quit()

        # OAuth callback: no token, state-validated instead.
        if path == "/callback" and method == "GET":
            self._handle_callback(query)
            return

        # Static / index: no token required.
        if method == "GET" and (path == "/" or not path.startswith("/api/")):
            self._serve_static(path)
            return

        # /api/local/* requires the local token.
        if path.startswith("/api/local/"):
            if not self._has_token():
                self._send_json(401, {"error": "missing or invalid token"})
                return
            handler = _resolve_route(method, path)
            if handler is None:
                self._send_json(404, {"error": f"no route for {method} {path}"})
                return
            try:
                body = self._read_json_body() if method in ("POST", "PUT", "DELETE") else None
                result = handler(self.server, path, query, body)
            except _routes.RouteError as e:
                self._send_json(e.status, {"error": str(e)})
                return
            except Exception as e:
                self._send_json(500, {"error": f"{type(e).__name__}: {e}"})
                return
            status = 204 if result is None else 200
            if status == 204:
                self.send_response(204)
                self.end_headers()
            else:
                self._send_json(status, result)
            return

        self._send_json(404, {"error": f"no route for {method} {path}"})

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    # ---- static assets ----

    def _serve_static(self, path: str) -> None:
        if path == "/" or path == "":
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        bundle = self.server.ui_bundle
        asset = bundle.read(rel)
        if asset is None and rel != "index.html":
            # SPA-style fallback so deep-linked routes land on index.
            asset = bundle.read("index.html")
        if asset is None:
            self._send_text(404, "Not found")
            return
        body, content_type = asset
        # Inject the local token + available source logos into index.html before serving.
        if rel == "index.html" or rel == "":
            logo_slugs = bundle.list_dir("logos", suffix=".svg")
            logo_colors: dict[str, str] = {}
            colors_asset = bundle.read("logos/colors.json")
            if colors_asset is not None:
                try:
                    logo_colors = json.loads(colors_asset[0])
                except (json.JSONDecodeError, ValueError):
                    logo_colors = {}
            token_tag = (
                f'<script>window.__DINOBASE_TOKEN__ = {json.dumps(self.server.local_token)};'
                f'window.__DINOBASE_PORT__ = {self.server.server_address[1]};'
                f'window.__DINOBASE_LOGOS__ = {json.dumps(logo_slugs)};'
                f'window.__DINOBASE_LOGO_COLORS__ = {json.dumps(logo_colors)};</script>'
            ).encode()
            body = body.replace(b"<!--DINOBASE_TOKEN-->", token_tag)
        self._send_bytes(200, body, content_type)

    # ---- OAuth callback ----

    def _handle_callback(self, query: dict[str, str]) -> None:
        state = query.get("state", "")
        code = query.get("code", "")
        error = query.get("error", "")

        if error:
            self._render_callback_page(
                "Sign-in failed",
                f"The provider returned an error: {error}.",
                ok=False,
            )
            return

        # Cloud login flow returns tokens as query params directly.
        cloud_payload = self.server.pop_cloud_login(state)
        if cloud_payload is not None:
            try:
                _routes.complete_cloud_login(self.server, query)
            except _routes.RouteError as e:
                self._render_callback_page("Sign-in failed", str(e), ok=False)
                return
            self._render_callback_page(
                "Signed in to Dinobase Cloud",
                "You can close this tab and return to the setup window.",
                ok=True,
                kind="cloud-login",
            )
            return

        oauth_payload = self.server.pop_oauth(state)
        if oauth_payload is None:
            self._render_callback_page(
                "Unknown or expired request",
                "This OAuth state isn't recognized. Try again from the setup window.",
                ok=False,
            )
            return

        if not code:
            self._render_callback_page(
                "No authorization code",
                "The provider did not return a code. Try again.",
                ok=False,
            )
            return

        try:
            _routes.complete_source_oauth(
                self.server, oauth_payload, code, ctx=query.get("ctx", ""),
            )
        except _routes.RouteError as e:
            self._render_callback_page("Couldn't connect source", str(e), ok=False)
            return

        self._render_callback_page(
            "Connected!",
            f"{oauth_payload.get('source_name', 'Source')} is now connected. You can close this tab.",
            ok=True,
            kind="oauth",
            source=oauth_payload.get("source_name", ""),
        )

    def _render_callback_page(
        self,
        title: str,
        message: str,
        *,
        ok: bool,
        kind: str = "",
        source: str = "",
    ) -> None:
        color = "#10b981" if ok else "#ef4444"
        emoji = "✅" if ok else "⚠️"
        payload = json.dumps({"type": f"dinobase-{kind}", "ok": ok, "source": source})
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{
    font-family: -apple-system, system-ui, sans-serif;
    text-align: center; padding: 60px 20px; color: #111;
  }}
  h1 {{ color: {color}; margin-bottom: 8px; }}
  p  {{ color: #555; max-width: 420px; margin: 8px auto; }}
</style></head>
<body>
  <h1>{emoji} {title}</h1>
  <p>{message}</p>
  <script>
    try {{
      if (window.opener) window.opener.postMessage({payload}, "*");
    }} catch (e) {{}}
    setTimeout(function () {{ window.close(); }}, 1200);
  </script>
</body></html>"""
        self._send_text(200 if ok else 400, html, "text/html; charset=utf-8")


def _resolve_route(method: str, path: str) -> Callable | None:
    """Return the route handler for (method, path), or None."""
    # Exact matches first.
    exact = _routes.EXACT_ROUTES.get((method, path))
    if exact is not None:
        return exact
    # Prefix matches for dynamic segments (e.g., /api/local/sources/{name}).
    for (m, prefix), handler in _routes.PREFIX_ROUTES.items():
        if m == method and path.startswith(prefix):
            return handler
    return None


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url, new=1, autoraise=True)
    except Exception:
        pass


def _bind(preferred_port: int, ui_bundle: UIBundle) -> SetupServer:
    """Bind the HTTP server, preferring the requested port if non-zero."""
    try:
        return SetupServer(("127.0.0.1", preferred_port), SetupHandler, ui_bundle)
    except OSError as e:
        if preferred_port == 0:
            raise
        # Fall back to a random port if the preferred one is taken.
        print(
            f"Port {preferred_port} is in use ({e}); falling back to a random port.",
            file=sys.stderr,
        )
        return SetupServer(("127.0.0.1", 0), SetupHandler, ui_bundle)


def run_setup_server(port: int = 0, open_browser: bool = True) -> None:
    """Start the setup server on localhost and block until it quits.

    Stops on Ctrl+C or when `/api/local/quit` is called (the browser tab
    fires this on `pagehide` when closed).
    """
    ui_bundle = resolve_ui_bundle(__version__)
    server = _bind(port, ui_bundle)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/?token={server.local_token}"

    print("Dinobase setup running.", file=sys.stderr)
    print(f"  URL: {url}", file=sys.stderr)
    print(f"  UI: {ui_bundle.version} ({ui_bundle.kind})", file=sys.stderr)
    print("  Close the browser tab or press Ctrl+C to quit.", file=sys.stderr)

    from dinobase import telemetry
    telemetry.capture("setup_ui_started", {
        "surface": "setup_ui",
        "ui_version": ui_bundle.version,
        "ui_source": ui_bundle.kind,
        "port": actual_port,
    })

    if open_browser:
        _open_browser(url)

    thread = threading.Thread(target=server.serve_forever, name="dinobase-setup", daemon=True)
    thread.start()
    try:
        while not server.quit_event.wait(timeout=0.25):
            scheduled = server.quit_scheduled_at
            if scheduled is not None and time.time() - scheduled >= QUIT_GRACE_SECONDS:
                print("\nBrowser tab closed; stopping setup server.", file=sys.stderr)
                break
    except KeyboardInterrupt:
        print("\nStopping setup server.", file=sys.stderr)
    finally:
        server.shutdown()
        server.server_close()
