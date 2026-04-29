"""YAML-to-dlt translator — converts YAML connector configs into dlt rest_api_source configs.

This is the bridge between our YAML spec and dlt's rest_api_source.
It handles:
- Credential substitution ({api_key} → actual value)
- Auth method resolution (named auth methods, per-resource overrides)
- Pagination config
- Incremental loading
- Nested/child resources (parent → child path parameter substitution)
- Resource selection (--resources flag)
- Multiple base URLs per resource
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from dinobase.sync.source_config import CONFIGS_DIR


def load_yaml_config(source_name: str) -> dict[str, Any] | None:
    """Load a YAML source config by name.

    Delegates to source_config.load_source_config() which checks
    the user's local connectors dir first, then the package configs dir.
    """
    from dinobase.sync.source_config import load_source_config

    return load_source_config(source_name)


def build_dlt_source(
    source_name: str,
    credentials: dict[str, str],
    resource_names: list[str] | None = None,
) -> Any:
    """Build a dlt source from a YAML config.

    Args:
        source_name: Name of the source (matches YAML filename)
        credentials: Dict of credential values (from user config)
        resource_names: Optional list of resources to include. None = all selected.

    Returns: A dlt source ready to run in a pipeline.
    """
    config = load_yaml_config(source_name)
    if config is None:
        raise ValueError(f"No YAML config found for source '{source_name}'")

    dlt_config = _translate_config(config, credentials)

    # Filter resources if requested
    if resource_names:
        dlt_config["resources"] = [
            r for r in dlt_config["resources"]
            if (r["name"] if isinstance(r, dict) else r) in resource_names
        ]

    from dlt.sources.rest_api import rest_api_source
    return rest_api_source(dlt_config, name=source_name)


def _translate_config(
    config: dict[str, Any], credentials: dict[str, str]
) -> dict[str, Any]:
    """Translate a YAML config into a dlt rest_api_source config dict."""

    client_config = config.get("client", {})
    auth_methods = config.get("auth_methods", {})
    resource_defaults = config.get("resource_defaults", {})
    resources = config.get("resources", [])

    # Build the dlt config
    dlt_config: dict[str, Any] = {
        "client": _build_client(client_config, credentials),
    }

    if resource_defaults:
        dlt_config["resource_defaults"] = _build_resource_defaults(resource_defaults, credentials)

    # Build resources
    dlt_resources = []
    parent_map: dict[str, dict] = {}  # name → resource config for parent lookups

    for resource in resources:
        # Skip unselected resources (unless explicitly requested)
        if not resource.get("selected", True):
            continue

        dlt_resource = _build_resource(resource, client_config, auth_methods, credentials)
        dlt_resources.append(dlt_resource)
        parent_map[resource["name"]] = dlt_resource

    # Resolve parent references (nested resources)
    for dlt_resource in dlt_resources:
        _resolve_parent(dlt_resource, parent_map)

    dlt_config["resources"] = dlt_resources
    return dlt_config


def _build_client(
    client_config: dict[str, Any], credentials: dict[str, str]
) -> dict[str, Any]:
    """Build the dlt client config with credential substitution."""
    client = {}

    if "base_url" in client_config:
        client["base_url"] = _substitute(client_config["base_url"], credentials)

    if "auth" in client_config:
        client["auth"] = _build_auth(client_config["auth"], credentials)

    if "paginator" in client_config:
        client["paginator"] = _build_paginator(client_config["paginator"])

    if "headers" in client_config:
        client["headers"] = {
            k: _substitute(v, credentials)
            for k, v in client_config["headers"].items()
        }

    return client


def _build_auth(auth_config: dict[str, Any], credentials: dict[str, str]) -> dict[str, Any]:
    """Build a dlt auth config with credential substitution."""
    auth = {}
    for key, value in auth_config.items():
        if isinstance(value, str):
            auth[key] = _substitute(value, credentials)
        else:
            auth[key] = value
    return auth


def _build_paginator(paginator_config: dict[str, Any]) -> dict[str, Any]:
    """Build a dlt paginator config."""
    # dlt uses specific field names for different paginator types
    pag = dict(paginator_config)

    # Map our field names to dlt's expected fields
    type_map = {
        "json_link": "json_link",
        "header_link": "header_link",
        "cursor": "cursor",
        "offset": "offset",
        "page_number": "page_number",
        "single_page": "single_page",
        "auto": "auto",
    }
    if "type" in pag:
        pag["type"] = type_map.get(pag["type"], pag["type"])

    return pag


def _build_resource_defaults(
    defaults: dict[str, Any], credentials: dict[str, str]
) -> dict[str, Any]:
    """Build resource defaults."""
    result = {}
    for key, value in defaults.items():
        if key == "endpoint" and isinstance(value, dict):
            result["endpoint"] = _build_endpoint(value, credentials)
        else:
            result[key] = value
    return result


def _build_resource(
    resource: dict[str, Any],
    client_config: dict[str, Any],
    auth_methods: dict[str, Any],
    credentials: dict[str, str],
) -> dict[str, Any]:
    """Build a single dlt resource config."""
    dlt_resource: dict[str, Any] = {"name": resource["name"]}

    # Endpoint config
    endpoint = resource.get("endpoint", {})
    dlt_endpoint = _build_endpoint(endpoint, credentials)

    # Override base_url if specified on the endpoint
    if "base_url" in endpoint:
        # dlt doesn't support per-resource base_url directly in rest_api_source,
        # but we can prepend it to the path
        base = _substitute(endpoint["base_url"], credentials).rstrip("/")
        path = dlt_endpoint.get("path", "").lstrip("/")
        dlt_endpoint["path"] = f"{base}/{path}"

    # Resolve auth override
    auth_ref = resource.get("auth")
    if auth_ref and auth_methods and auth_ref in auth_methods:
        # Named auth method — not directly supported by dlt rest_api per-resource,
        # but we can set it as endpoint headers for basic/bearer
        resolved_auth = auth_methods[auth_ref]
        # For now, store as metadata — the write client uses this
        dlt_resource["_auth_method"] = auth_ref

    # Incremental loading
    incremental = resource.get("incremental")
    if incremental:
        dlt_incremental = {
            "cursor_path": incremental["cursor_path"],
            "initial_value": incremental.get("initial_value"),
        }
        dlt_endpoint["incremental"] = dlt_incremental

        # If the resource has params with {incremental.start_value}, keep them
        # dlt handles this substitution automatically

    dlt_resource["endpoint"] = dlt_endpoint

    # Primary key
    if "primary_key" in resource:
        dlt_resource["primary_key"] = resource["primary_key"]

    # Write disposition
    if "write_disposition" in resource:
        dlt_resource["write_disposition"] = resource["write_disposition"]

    # Store parent info for later resolution
    if "parent" in resource:
        dlt_resource["_parent"] = resource["parent"]

    return dlt_resource


def _build_endpoint(
    endpoint: dict[str, Any], credentials: dict[str, str]
) -> dict[str, Any]:
    """Build an endpoint config with credential substitution in params."""
    dlt_endpoint: dict[str, Any] = {}

    if "path" in endpoint:
        dlt_endpoint["path"] = _substitute(endpoint["path"], credentials)

    if "method" in endpoint:
        dlt_endpoint["method"] = endpoint["method"]

    if "params" in endpoint:
        dlt_endpoint["params"] = {
            k: _substitute(str(v), credentials) if isinstance(v, str) else v
            for k, v in endpoint["params"].items()
        }

    if "data_selector" in endpoint:
        dlt_endpoint["data_selector"] = endpoint["data_selector"]

    if "headers" in endpoint:
        dlt_endpoint["headers"] = {
            k: _substitute(v, credentials)
            for k, v in endpoint["headers"].items()
        }

    return dlt_endpoint


def _resolve_parent(
    resource: dict[str, Any], parent_map: dict[str, dict]
) -> None:
    """Resolve parent references for nested resources.

    Converts our parent config into dlt's include_from_parent format.
    """
    parent_info = resource.pop("_parent", None)
    if parent_info is None:
        return

    parent_name = parent_info["resource"]
    parent_field = parent_info["field"]
    param_name = parent_info["param"]

    if parent_name not in parent_map:
        print(
            f"  Warning: parent resource '{parent_name}' not found for "
            f"child '{resource['name']}'",
            file=sys.stderr,
        )
        return

    # dlt nested resource format: the path contains {param} which gets
    # substituted from the parent's field. We need to tell dlt about this
    # via include_from_parent.
    resource["include_from_parent"] = [parent_field]

    # The path already has {param_name} — dlt resolves it from parent data
    # We need to reference the parent resource by name
    endpoint = resource.get("endpoint", {})
    path = endpoint.get("path", "")

    # Replace our {param} syntax with dlt's expected format
    # dlt uses the parent resource's data to resolve path params
    resource["endpoint"] = endpoint

    # Set up the parent-child relationship in dlt format
    # dlt expects: {"name": "child", "endpoint": {"path": "parent/{id}/child"},
    #               "include_from_parent": ["id"]}
    # The parent resource must be referenced by name in the resources list


def _substitute(template: str, credentials: dict[str, str]) -> str:
    """Substitute {credential_name} placeholders with actual values."""
    def replacer(match):
        key = match.group(1)
        # Don't substitute dlt-internal templates like {incremental.start_value}
        if "." in key:
            return match.group(0)
        return credentials.get(key, match.group(0))

    return re.sub(r"\{(\w+(?:\.\w+)*)\}", replacer, template)


def get_write_endpoints(source_name: str) -> list[dict[str, Any]]:
    """Get write endpoints from a YAML config."""
    config = load_yaml_config(source_name)
    if config is None:
        return []

    # New format: write_endpoints key
    write_eps = config.get("write_endpoints", [])
    if write_eps:
        return write_eps

    # Legacy format: endpoints with write: true
    return [
        ep for ep in config.get("endpoints", [])
        if ep.get("write", False)
    ]
