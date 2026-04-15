"""Thin live proxy to the MCP Registry.

Forwards a single `GET /v0.1/servers` request per call, normalizing each
server record into the shape the setup UI understands. The registry
supports `search=<substring>` and `version=latest`, so we don't cache
anything — the setup UI debounces the user's query against this module.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"
SOURCE_ID = "mcp_registry"
PAGE_TIMEOUT = 10.0
DEFAULT_LIMIT = 50
MAX_LIMIT = 100  # Registry caps `limit` at 100.

USER_AGENT = "dinobase-setup-ui-mcp-catalog/3"

REFERENCE_PREFIX = "io.modelcontextprotocol/"


class CatalogError(RuntimeError):
    """A user-visible catalog-fetch error."""


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _http_get_json(url: str) -> Any:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=PAGE_TIMEOUT) as resp:
            raw = resp.read()
    except HTTPError as e:
        raise CatalogError(f"registry error: {e.code} {e.reason}") from e
    except URLError as e:
        raise CatalogError(f"network error: {e.reason}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise CatalogError(f"invalid JSON from registry: {e}") from e


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return slug or "entry"


def _command_from_package(pkg: dict) -> str | None:
    registry_type = pkg.get("registryType")
    identifier = pkg.get("identifier")
    version = pkg.get("version") or ""
    runtime_hint = pkg.get("runtimeHint")
    if not identifier:
        return None
    if registry_type == "npm":
        return f"npx -y {identifier}"
    if registry_type == "pypi":
        return f"uvx {identifier}"
    if registry_type == "oci":
        tag = f":{version}" if version else ""
        return f"docker run --rm -i {identifier}{tag}"
    if runtime_hint:
        return f"{runtime_hint} {identifier}"
    return None


def _env_from_package(pkg: dict) -> list[dict]:
    out: list[dict] = []
    for var in pkg.get("environmentVariables") or []:
        if not isinstance(var, dict) or not var.get("name"):
            continue
        out.append(
            {
                "name": var["name"],
                "description": var.get("description") or "",
                "required": bool(var.get("isRequired")),
                "secret": bool(var.get("isSecret")),
            }
        )
    return out


def _env_from_remote_headers(remote: dict) -> list[dict]:
    out: list[dict] = []
    for header in remote.get("headers") or []:
        if not isinstance(header, dict) or not header.get("name"):
            continue
        out.append(
            {
                "name": header["name"],
                "description": header.get("description") or "",
                "required": bool(header.get("isRequired")),
                "secret": bool(header.get("isSecret")),
            }
        )
    return out


def _remote_transport(remote_type: str | None) -> str:
    if remote_type == "streamable-http":
        return "streamable_http"
    if remote_type == "sse":
        return "sse"
    return "stdio"


def _homepage(server: dict) -> str:
    if server.get("websiteUrl"):
        return server["websiteUrl"]
    repo = server.get("repository")
    if isinstance(repo, dict) and repo.get("url"):
        return repo["url"]
    return ""


def _normalize_server(server: dict) -> dict | None:
    name = server.get("name")
    if not name:
        return None

    packages = server.get("packages") or []
    remotes = server.get("remotes") or []

    transport = "stdio"
    command: str | None = None
    url = ""
    env: list[dict] = []

    if packages:
        pkg = packages[0]
        transport_obj = pkg.get("transport") or {}
        transport = transport_obj.get("type") or "stdio"
        if transport not in ("stdio", "sse", "streamable_http"):
            transport = "stdio"
        command = _command_from_package(pkg)
        env = _env_from_package(pkg)
    elif remotes:
        remote = remotes[0]
        transport = _remote_transport(remote.get("type"))
        url = remote.get("url") or ""
        env = _env_from_remote_headers(remote)
    else:
        return None

    category = "reference" if name.startswith(REFERENCE_PREFIX) else "community"

    return {
        "source": SOURCE_ID,
        "category": category,
        "id": _slugify(name),
        "registry_name": name,
        "name": server.get("title") or name,
        "description": server.get("description") or "",
        "transport": transport,
        "command": command,
        "url": url,
        "env": env,
        "homepage": _homepage(server),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_catalog(
    query: str = "",
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Forward one page of registry results, normalized.

    Returns `{entries, next_cursor}`. `next_cursor` is omitted when there
    are no more pages.
    """
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    params: dict[str, str] = {"version": "latest", "limit": str(limit)}
    if query:
        params["search"] = query
    if cursor:
        params["cursor"] = cursor

    data = _http_get_json(f"{REGISTRY_URL}?{urlencode(params)}")
    if not isinstance(data, dict):
        raise CatalogError("unexpected registry response shape")

    entries: list[dict] = []
    seen_ids: dict[str, int] = {}
    for record in data.get("servers") or []:
        meta = ((record or {}).get("_meta") or {}).get(
            "io.modelcontextprotocol.registry/official"
        ) or {}
        if meta.get("status") != "active":
            continue
        normalized = _normalize_server((record or {}).get("server") or {})
        if not normalized:
            continue
        base_id = normalized["id"]
        count = seen_ids.get(base_id, 0)
        if count:
            normalized["id"] = f"{base_id}_{count + 1}"
        seen_ids[base_id] = count + 1
        entries.append(normalized)

    next_cursor = (data.get("metadata") or {}).get("nextCursor") or None
    result: dict[str, Any] = {"entries": entries}
    if next_cursor:
        result["next_cursor"] = next_cursor
    return result
