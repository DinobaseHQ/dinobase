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


def _substitute(template: str, credentials: dict[str, str]) -> str:
    """Replace {key} placeholders in a string with credential values."""
    result = template
    for key, value in credentials.items():
        result = result.replace(f"{{{key}}}", value)
    return result


def build_client_auth_headers(
    config: dict[str, Any],
    credentials: dict[str, str],
) -> dict[str, str]:
    """Build auth headers from a resource-style YAML config's client.auth block.

    Handles the format used by configs like intercom.yaml, chargebee.yaml:
        client:
          auth:
            type: bearer
            token: "{token}"
    """
    import base64

    client = config.get("client", {})
    auth = client.get("auth", {})
    auth_type = auth.get("type", "")

    if auth_type == "bearer":
        token_template = auth.get("token", "")
        token = _substitute(token_template, credentials)
        return {"Authorization": f"Bearer {token}"}
    elif auth_type == "http_basic":
        username = _substitute(auth.get("username", ""), credentials)
        password = _substitute(auth.get("password", ""), credentials)
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    elif auth_type == "api_key_header":
        header = auth.get("header", "Authorization")
        value = _substitute(auth.get("value", ""), credentials)
        return {header: value}

    return {}


def get_client_base_url(
    config: dict[str, Any],
    credentials: dict[str, str],
) -> str:
    """Get the base URL from a resource-style config, substituting credentials."""
    base_url = config.get("client", {}).get("base_url", "")
    return _substitute(base_url, credentials).rstrip("/")


def get_client_headers(
    config: dict[str, Any],
    credentials: dict[str, str],
) -> dict[str, str]:
    """Get extra client headers (e.g., API version pins) from a resource-style config."""
    headers = config.get("client", {}).get("headers", {})
    return {k: _substitute(str(v), credentials) for k, v in headers.items()}


def get_resource(config: dict[str, Any], table_name: str) -> dict[str, Any] | None:
    """Find a resource by table name in a resource-style config."""
    for resource in config.get("resources", []):
        if resource.get("name") == table_name:
            return resource
    return None


def get_resource_primary_key(config: dict[str, Any], resource: dict[str, Any]) -> str:
    """Get the primary key for a resource (falls back to resource_defaults)."""
    pk = resource.get("primary_key")
    if pk:
        return pk
    return config.get("resource_defaults", {}).get("primary_key", "id")


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
