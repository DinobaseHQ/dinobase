"""Request handlers for the /api/local/* JSON API.

Each handler takes ``(server, path, query, body)`` and returns a JSON-serialisable
value (or None for 204). Raise ``RouteError`` for client-visible errors.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from typing import Any
from urllib.parse import unquote, urlencode

import yaml

from dinobase import __version__
from dinobase import auth as _auth
from dinobase import config as _config
from dinobase import telemetry as _telemetry
from dinobase.config import get_connectors_dir
from dinobase.connectors.templates import (
    build_mcp_connector_yaml,
    build_rest_connector_yaml,
)
from dinobase.setup_server import mcp_catalog as _mcp_catalog
from dinobase.sync.registry import SOURCES, get_source_entry


def _capture(event: str, props: dict[str, Any] | None = None) -> None:
    """Fire a telemetry event tagged with surface=setup_ui. Never raises."""
    merged = {"surface": "setup_ui"}
    if props:
        merged.update(props)
    _telemetry.capture(event, merged)


class RouteError(Exception):
    """Client-visible error with an HTTP status code."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Status / config
# ---------------------------------------------------------------------------


def status(server, path, query, body):
    logged_in = _config.is_cloud_logged_in()
    creds = _config.load_cloud_credentials() if logged_in else None
    return {
        "version": __version__,
        "mode": "local",
        "cloud_hosted_available": False,
        "cloud_logged_in": logged_in,
        "cloud_email": (creds or {}).get("email", ""),
        "port": server.server_address[1],
        "ui_version": server.ui_bundle.version,
        "ui_source": server.ui_bundle.kind,
    }


def get_config(server, path, query, body):
    return _config.load_config()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def registry(server, path, query, body):
    return {
        "sources": [entry.to_dict() for _, entry in sorted(SOURCES.items())],
    }


def providers(server, path, query, body):
    # List of OAuth-capable sources from the registry (no network call needed).
    return {
        "providers": [
            entry.to_dict() for _, entry in sorted(SOURCES.items())
            if entry.supports_oauth
        ],
    }


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def list_sources(server, path, query, body):
    connectors = _config.get_connectors()
    return {"connectors": [{"name": name, **cfg} for name, cfg in connectors.items()]}


def add_source(server, path, query, body):
    if not isinstance(body, dict):
        raise RouteError("expected JSON object body")
    name = (body.get("name") or body.get("type") or "").strip()
    source_type = (body.get("type") or "").strip()
    credentials = body.get("credentials") or {}

    if not source_type:
        raise RouteError("missing 'type'")
    if not name:
        raise RouteError("missing 'name'")
    if not isinstance(credentials, dict):
        raise RouteError("'credentials' must be an object")

    entry = get_source_entry(source_type)
    if entry is None:
        raise RouteError(f"unknown connector type: {source_type}", status=404)

    # Validate required credential params.
    missing = [p.name for p in entry.credentials if not credentials.get(p.name)]
    if missing:
        raise RouteError(f"missing credentials: {', '.join(missing)}")

    # v1: always local. Cloud-hosted mode is TBD.
    _config.init_dinobase()
    _config.add_connector(
        name=name,
        connector_type=source_type,
        credentials={k: str(v) for k, v in credentials.items()},
        sync_interval=body.get("sync_interval") or None,
        freshness_threshold=body.get("freshness_threshold") or None,
    )
    _capture("source_added", {
        "source_type": source_type,
        "auth_method": "api_key",
        "is_cloud_mode": False,
    })
    return {"name": name, "type": source_type, "status": "added"}


def delete_source(server, path, query, body):
    name = path.rsplit("/", 1)[-1]
    if not name:
        raise RouteError("missing connector name")
    connectors = _config.get_connectors()
    if name not in connectors:
        raise RouteError(f"connector '{name}' not found", status=404)
    source_type = (connectors.get(name) or {}).get("type", "")
    _config.remove_connector(name)
    _capture("source_removed", {"source_type": source_type})
    return None  # 204


def start_source_oauth(server, path, query, body):
    # POST /api/local/sources/{name}/oauth/start
    # path = "/api/local/sources/hubspot/oauth/start"
    parts = path.split("/")
    try:
        idx = parts.index("sources")
        source_type = parts[idx + 1]
    except (ValueError, IndexError):
        raise RouteError("invalid path")

    if not source_type:
        raise RouteError("missing source type")

    entry = get_source_entry(source_type)
    if entry is None:
        raise RouteError(f"unknown source type: {source_type}", status=404)
    if not entry.supports_oauth:
        raise RouteError(f"{source_type} does not support OAuth")

    source_name = (body or {}).get("name") or source_type

    state = secrets.token_urlsafe(32)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"

    server.remember_oauth(state, {
        "source_name": source_name,
        "source_type": source_type,
        "redirect_uri": redirect_uri,
    })

    proxy_url = _auth.get_proxy_url()
    auth_url = f"{proxy_url}/auth/{source_type}?" + urlencode({
        "redirect_uri": redirect_uri,
        "state": state,
    })
    _capture("source_oauth_started", {"source_type": source_type})
    return {"auth_url": auth_url, "state": state}


def complete_source_oauth(
    server,
    payload: dict[str, Any],
    code: str,
    ctx: str = "",
) -> None:
    """Called from the /callback handler after the provider redirects back.

    Exchanges the code for tokens via the OAuth proxy, then persists the
    resulting credentials. When the user is signed in to Dinobase Cloud, the
    tokens are uploaded to the cloud API (encrypted at rest, shared across
    machines). Otherwise they're written to the local config.yaml.

    ``ctx`` is the opaque blob the proxy returned in the /callback redirect
    (PKCE verifier + tenant subdomain, Fernet-sealed).
    """
    source_type = payload["source_type"]
    source_name = payload["source_name"]
    redirect_uri = payload["redirect_uri"]

    try:
        tokens = _auth.exchange_code(source_type, code, redirect_uri, ctx=ctx)
    except RuntimeError as e:
        raise RouteError(str(e))

    expires_at = ""
    if "expires_in" in tokens:
        expires_at = str(int(time.time()) + int(tokens["expires_in"]))

    credentials = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": expires_at,
        "auth_method": "oauth",
    }

    # Prefer cloud persistence so tokens follow the user across machines.
    if _config.is_cloud_logged_in():
        try:
            _upload_credentials_to_cloud(source_name, source_type, credentials)
            _capture("source_added", {
                "source_type": source_type,
                "auth_method": "oauth",
                "is_cloud_mode": True,
            })
            return
        except RuntimeError as e:
            # Fall back to local so the user isn't stranded.
            print(
                f"Warning: couldn't save credentials to Dinobase Cloud "
                f"({e}); storing locally instead.",
                file=sys.stderr,
            )

    _config.init_dinobase()
    _config.add_connector(source_name, source_type, credentials)
    _capture("source_added", {
        "source_type": source_type,
        "auth_method": "oauth",
        "is_cloud_mode": False,
    })


def _upload_credentials_to_cloud(
    source_name: str,
    source_type: str,
    credentials: dict[str, str],
) -> None:
    """POST encrypted credentials to the cloud API so they sync across machines."""
    from dinobase.cloud_client import CloudClient

    token = _config.ensure_fresh_cloud_token()
    if not token:
        raise RuntimeError("not logged in to Dinobase Cloud")
    api_url = _config.get_cloud_api_url()
    client = CloudClient(api_url, token)
    client.add_connector(source_name, source_type, credentials)


# ---------------------------------------------------------------------------
# Custom connectors (REST + MCP)
# ---------------------------------------------------------------------------


def create_mcp_connector(server, path, query, body):
    if not isinstance(body, dict):
        raise RouteError("expected JSON object body")
    name = (body.get("name") or "").strip()
    transport = (body.get("transport") or "").strip()
    if not name:
        raise RouteError("missing 'name'")
    if not transport:
        raise RouteError("missing 'transport'")

    env_raw = body.get("env")
    env: dict[str, str] | None = None
    if env_raw is not None:
        if not isinstance(env_raw, dict):
            raise RouteError("'env' must be an object of string->string")
        env = {}
        for k, v in env_raw.items():
            if not isinstance(k, str) or not k.strip():
                raise RouteError("'env' keys must be non-empty strings")
            env[k.strip()] = "" if v is None else str(v)

    try:
        content = build_mcp_connector_yaml(
            name=name,
            transport=transport,
            command=body.get("command"),
            url=body.get("url"),
            mode=body.get("mode", "live"),
            env=env,
        )
    except ValueError as e:
        raise RouteError(str(e))

    result = _write_connector(name, content)
    _capture("custom_connector_created", {"kind": "mcp", "transport": transport})
    return result


def create_rest_connector(server, path, query, body):
    if not isinstance(body, dict):
        raise RouteError("expected JSON object body")
    name = (body.get("name") or "").strip()
    if not name:
        raise RouteError("missing 'name'")

    auth_type = body.get("auth_type", "bearer")
    content = build_rest_connector_yaml(
        name=name,
        url=body.get("url"),
        auth_type=auth_type,
        endpoint=body.get("endpoint"),
        data_selector=body.get("data_selector", "$"),
        mode=body.get("mode", "auto"),
    )
    result = _write_connector(name, content)
    _capture("custom_connector_created", {"kind": "rest", "auth_type": auth_type})
    return result


def list_mcp_catalog(server, path, query, body):
    try:
        result = _mcp_catalog.search_catalog(
            query=query.get("q", ""),
            cursor=query.get("cursor") or None,
            limit=int(query.get("limit") or _mcp_catalog.DEFAULT_LIMIT),
        )
    except _mcp_catalog.CatalogError as e:
        raise RouteError(f"could not fetch MCP catalog: {e}", status=502)
    except ValueError:
        raise RouteError("invalid limit", status=400)
    return {"source": _mcp_catalog.SOURCE_ID, **result}


def _write_connector(name: str, content: str) -> dict[str, str]:
    connectors_dir = get_connectors_dir()
    connectors_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = connectors_dir / f"{name}.yaml"
    if yaml_path.exists():
        raise RouteError(f"connector '{name}' already exists at {yaml_path}", status=409)
    yaml_path.write_text(content)
    return {"name": name, "path": str(yaml_path), "status": "created"}


def _connector_kind(parsed: dict[str, Any] | None) -> str:
    if not isinstance(parsed, dict):
        return "unknown"
    if "transport" in parsed:
        return "mcp"
    return "rest"


def _connector_summary(path, parsed, raw):
    kind = _connector_kind(parsed)
    summary: dict[str, Any] = {
        "name": (parsed or {}).get("name") or path.stem,
        "kind": kind,
        "description": (parsed or {}).get("description", ""),
        "path": str(path),
        "raw": raw,
    }
    if parsed is None:
        summary["parse_error"] = True
        return summary
    if kind == "mcp":
        transport = parsed.get("transport") or {}
        summary["transport"] = transport.get("type", "")
        summary["mode"] = parsed.get("mode", "live")
        if transport.get("type") == "stdio":
            cmd_parts = [transport.get("command", "")] + list(transport.get("args") or [])
            summary["command"] = " ".join(p for p in cmd_parts if p)
        else:
            summary["url"] = transport.get("url", "")
    else:
        client = parsed.get("client") or {}
        auth = client.get("auth") or {}
        defaults_endpoint = (parsed.get("resource_defaults") or {}).get("endpoint") or {}
        resources = parsed.get("resources") or []
        first = resources[0] if resources and isinstance(resources[0], dict) else {}
        first_endpoint = first.get("endpoint") or {}
        summary["base_url"] = client.get("base_url", "")
        summary["auth_type"] = auth.get("type", "bearer")
        summary["mode"] = parsed.get("mode", "auto")
        summary["endpoint"] = first_endpoint.get("path", "")
        summary["data_selector"] = (
            first_endpoint.get("data_selector") or defaults_endpoint.get("data_selector") or "$"
        )
        summary["resources"] = [
            r.get("name", "") for r in resources if isinstance(r, dict)
        ]
    return summary


def _name_from_path(path: str, prefix: str) -> str:
    """Extract the `{name}` segment after `prefix` in a request path."""
    tail = path[len(prefix):] if path.startswith(prefix) else ""
    name = tail.split("/", 1)[0]
    return unquote(name)


def _validate_connector_name(name: str) -> None:
    if not name:
        raise RouteError("missing connector name")
    if "/" in name or "\\" in name or name.startswith(".") or name == "":
        raise RouteError("invalid connector name")


def list_connectors(server, path, query, body):
    connectors_dir = get_connectors_dir()
    if not connectors_dir.is_dir():
        return {"connectors": []}

    results = []
    for file_path in sorted(connectors_dir.glob("*.yaml")):
        if file_path.name.startswith("_"):
            continue
        try:
            raw = file_path.read_text()
        except OSError as e:
            results.append({
                "name": file_path.stem,
                "kind": "unknown",
                "path": str(file_path),
                "raw": "",
                "error": str(e),
            })
            continue
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            results.append({
                "name": file_path.stem,
                "kind": "unknown",
                "path": str(file_path),
                "raw": raw,
                "parse_error": str(e),
            })
            continue
        results.append(_connector_summary(file_path, parsed if isinstance(parsed, dict) else {}, raw))
    return {"connectors": results}


def get_connector(server, path, query, body):
    name = _name_from_path(path, "/api/local/connectors/")
    _validate_connector_name(name)
    yaml_path = get_connectors_dir() / f"{name}.yaml"
    if not yaml_path.exists():
        raise RouteError(f"connector '{name}' not found", status=404)
    raw = yaml_path.read_text()
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        return {
            "name": name,
            "kind": "unknown",
            "path": str(yaml_path),
            "raw": raw,
            "parse_error": str(e),
        }
    return _connector_summary(yaml_path, parsed if isinstance(parsed, dict) else {}, raw)


def update_connector(server, path, query, body):
    name = _name_from_path(path, "/api/local/connectors/")
    _validate_connector_name(name)
    if not isinstance(body, dict):
        raise RouteError("expected JSON object body")

    raw = body.get("raw")
    if raw is None:
        # Structured edit — regenerate YAML via the same builders used at
        # creation time. This overwrites any hand-edits the user made to the
        # file; they should use the raw-YAML toggle if they want to preserve
        # bespoke tweaks.
        kind = (body.get("kind") or "").strip()
        if kind == "mcp":
            try:
                raw = build_mcp_connector_yaml(
                    name=name,
                    transport=(body.get("transport") or "").strip(),
                    command=body.get("command"),
                    url=body.get("url"),
                    mode=body.get("mode", "live"),
                )
            except ValueError as e:
                raise RouteError(str(e))
        elif kind == "rest":
            raw = build_rest_connector_yaml(
                name=name,
                url=body.get("url"),
                auth_type=body.get("auth_type", "bearer"),
                endpoint=body.get("endpoint"),
                data_selector=body.get("data_selector") or "$",
                mode=body.get("mode", "auto"),
            )
        else:
            raise RouteError("missing 'raw' or connector 'kind'")

    if not isinstance(raw, str) or not raw.strip():
        raise RouteError("missing YAML content")

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise RouteError(f"invalid YAML: {e}")
    if not isinstance(parsed, dict):
        raise RouteError("connector YAML must be a mapping at the top level")

    yaml_path = get_connectors_dir() / f"{name}.yaml"
    if not yaml_path.exists():
        raise RouteError(f"connector '{name}' not found", status=404)
    yaml_path.write_text(raw)
    return _connector_summary(yaml_path, parsed, raw)


def delete_connector_route(server, path, query, body):
    name = _name_from_path(path, "/api/local/connectors/")
    _validate_connector_name(name)
    yaml_path = get_connectors_dir() / f"{name}.yaml"
    if not yaml_path.exists():
        raise RouteError(f"connector '{name}' not found", status=404)
    yaml_path.unlink()
    return None  # 204


# ---------------------------------------------------------------------------
# Cloud login
# ---------------------------------------------------------------------------


def cloud_status(server, path, query, body):
    logged_in = _config.is_cloud_logged_in()
    creds = _config.load_cloud_credentials() if logged_in else None
    return {
        "logged_in": logged_in,
        "email": (creds or {}).get("email", ""),
        "api_url": (creds or {}).get("api_url", _config.get_cloud_api_url()),
    }


def cloud_login_start(server, path, query, body):
    """Kick off the Dinobase Cloud sign-in flow through the setup server's /callback."""
    web_url = os.environ.get("DINOBASE_WEB_URL", "https://app.dinobase.ai")
    state = secrets.token_urlsafe(32)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"

    server.remember_cloud_login(state, {"redirect_uri": redirect_uri})

    login_url = f"{web_url}/cli-login?" + urlencode({
        "callback": redirect_uri,
        "state": state,
    })
    return {"login_url": login_url, "state": state}


def cloud_logout(server, path, query, body):
    _config.clear_cloud_credentials()
    return {"logged_in": False}


def complete_cloud_login(server, query_params: dict[str, str]) -> None:
    """Called from the /callback handler for the cloud-login flow."""
    access_token = query_params.get("access_token")
    if not access_token:
        raise RouteError("no access token returned from sign-in")

    credentials = {
        "access_token": access_token,
        "refresh_token": query_params.get("refresh_token", ""),
        "expires_at": int(query_params.get("expires_at", 0) or 0),
        "user_id": query_params.get("user_id", ""),
        "email": query_params.get("email", ""),
        "api_url": _config.get_cloud_api_url(),
    }
    _config.save_cloud_credentials(credentials)

    if credentials["user_id"]:
        _telemetry.identify(credentials["user_id"], credentials["email"] or None)
    _capture("login_completed", {"email": credentials["email"]})


# ---------------------------------------------------------------------------
# Quit
# ---------------------------------------------------------------------------


def quit_server(server, path, query, body):
    server.schedule_quit()
    _capture("setup_ui_closed")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Route tables (consumed by server.py dispatcher)
# ---------------------------------------------------------------------------


EXACT_ROUTES: dict[tuple[str, str], Any] = {
    ("GET", "/api/local/status"): status,
    ("GET", "/api/local/config"): get_config,
    ("GET", "/api/local/registry"): registry,
    ("GET", "/api/local/providers"): providers,
    ("GET", "/api/local/sources"): list_sources,
    ("POST", "/api/local/sources"): add_source,
    ("GET", "/api/local/connectors"): list_connectors,
    ("POST", "/api/local/mcp"): create_mcp_connector,
    ("GET", "/api/local/mcp/catalog"): list_mcp_catalog,
    ("POST", "/api/local/connectors/rest"): create_rest_connector,
    ("GET", "/api/local/cloud/status"): cloud_status,
    ("POST", "/api/local/cloud/login"): cloud_login_start,
    ("POST", "/api/local/cloud/logout"): cloud_logout,
    ("POST", "/api/local/quit"): quit_server,
}


# (method, prefix) — path must start with prefix. Longest prefix first.
PREFIX_ROUTES: dict[tuple[str, str], Any] = {
    ("POST", "/api/local/sources/"): None,  # populated below
    ("DELETE", "/api/local/sources/"): delete_source,
    ("GET", "/api/local/connectors/"): get_connector,
    ("PUT", "/api/local/connectors/"): update_connector,
    ("DELETE", "/api/local/connectors/"): delete_connector_route,
}


def _dispatch_source_post(server, path, query, body):
    # POST /api/local/sources/{name}/oauth/start
    if path.endswith("/oauth/start"):
        return start_source_oauth(server, path, query, body)
    raise RouteError(f"no route for POST {path}", status=404)


PREFIX_ROUTES[("POST", "/api/local/sources/")] = _dispatch_source_post
