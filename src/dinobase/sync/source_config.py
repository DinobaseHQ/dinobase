"""YAML-based source configuration loader.

Loads source configs from YAML files that map 1:1 to source APIs — both
read and write endpoints, multiple base URLs, per-endpoint auth methods.

This is the next-gen replacement for the Python registry. Each YAML file
fully describes a source's API surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


CONFIGS_DIR = Path(__file__).parent / "sources" / "configs"


def load_source_config(source_name: str) -> dict[str, Any] | None:
    """Load a YAML source config by name. Returns None if not found."""
    path = CONFIGS_DIR / f"{source_name}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def list_yaml_sources() -> list[str]:
    """List all source names that have YAML configs."""
    if not CONFIGS_DIR.exists():
        return []
    return sorted(
        p.stem for p in CONFIGS_DIR.glob("*.yaml")
        if not p.name.startswith("_")
    )


def get_read_endpoints(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all read endpoints from a source config."""
    return [
        ep for ep in config.get("endpoints", [])
        if not ep.get("write", False)
    ]


def get_write_endpoints(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all write endpoints from a source config."""
    return [
        ep for ep in config.get("endpoints", [])
        if ep.get("write", False)
    ]


def get_endpoint(config: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get a specific endpoint by name."""
    for ep in config.get("endpoints", []):
        if ep["name"] == name:
            return ep
    return None


def build_auth_headers(
    endpoint: dict[str, Any],
    credentials: dict[str, str],
) -> dict[str, str]:
    """Build auth headers for an endpoint based on its auth method."""
    import base64

    auth_type = endpoint.get("auth", "http_basic")
    api_key = credentials.get("api_key", "")
    secret_key = credentials.get("secret_key", "")

    if auth_type == "http_basic":
        encoded = base64.b64encode(f"{api_key}:{secret_key}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    elif auth_type == "bearer":
        token = credentials.get("token", secret_key)
        return {"Authorization": f"Bearer {token}"}
    elif auth_type == "api_key_header":
        return {"Authorization": f"Api-Key {secret_key}"}
    elif auth_type == "api_key_in_body":
        # Auth is in the request body, not headers
        return {}
    else:
        return {}


def build_request_body(
    endpoint: dict[str, Any],
    credentials: dict[str, str],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build request body, injecting auth if needed."""
    auth_type = endpoint.get("auth", "http_basic")
    body = dict(data)

    if auth_type == "api_key_in_body":
        body["api_key"] = credentials.get("api_key", "")

    return body


def build_url(
    endpoint: dict[str, Any],
    path_params: dict[str, str] | None = None,
) -> str:
    """Build the full URL for an endpoint, substituting path parameters."""
    base = endpoint.get("base_url", "").rstrip("/")
    path = endpoint.get("path", "").lstrip("/")

    # Substitute path parameters like {event_type}, {annotation_id}
    if path_params:
        for key, value in path_params.items():
            path = path.replace(f"{{{key}}}", value)

    return f"{base}/{path}"
