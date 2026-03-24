"""Source connectors for Dinobase.

Resolution order:
1. YAML config (src/dinobase/sync/sources/configs/<name>.yaml) → dlt rest_api_source
2. Registry entry (dlt verified source or built-in) → import and call
3. File sources (parquet, csv) → handled separately, no dlt pipeline

YAML configs are preferred because they support the full spec (incremental,
nested resources, write endpoints, resource selection).
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

from dinobase.sync.registry import get_source_entry
from dinobase.sync.yaml_source import load_yaml_config, build_dlt_source


def get_source(
    source_type: str,
    credentials: dict[str, str],
    resource_names: list[str] | None = None,
) -> Any:
    """Return a dlt source for the given source type.

    Args:
        source_type: Source name (e.g., "hubspot", "stripe", "amplitude")
        credentials: Credential values from user config
        resource_names: Optional list of resources to sync (None = all)
    """
    # File sources don't use dlt
    if source_type in ("parquet", "csv"):
        raise ValueError(
            f"File sources ({source_type}) don't use the sync engine. "
            f"Use `dinobase add {source_type} --path ...` instead."
        )

    # 1. Try YAML config first (full spec support)
    yaml_config = load_yaml_config(source_type)
    if yaml_config and "client" in yaml_config:
        print(f"  Using YAML config: configs/{source_type}.yaml", file=sys.stderr)
        return build_dlt_source(source_type, credentials, resource_names)

    # 2. Fall back to registry (dlt verified sources / built-in sources)
    entry = get_source_entry(source_type)
    if entry is None:
        from dinobase.sync.registry import list_available_sources
        available = ", ".join(list_available_sources())
        raise ValueError(f"Unknown source type: {source_type}. Available: {available}")

    # Check for missing pip dependencies
    if entry.pip_extra:
        try:
            importlib.import_module(entry.pip_extra.replace("-", "_"))
        except ImportError:
            raise ImportError(
                f"Source '{source_type}' requires an extra package. "
                f"Install it with: pip install {entry.pip_extra}"
            )

    # Import the source function
    module_path, func_name = entry.import_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(
            f"Could not import source '{source_type}' from {module_path}: {e}. "
            f"Make sure dlt-verified-sources is installed: pip install dlt-verified-sources"
        )
    source_func = getattr(module, func_name)

    # Map credentials to the source function's parameter names
    kwargs = dict(entry.extra_params)
    for param in entry.credentials:
        value = credentials.get(param.name) or credentials.get(param.cli_flag.lstrip("-").replace("-", "_"))
        if not value:
            for config_key in ("api_key", "token", "connection_string", "password", "secret_key"):
                if config_key in credentials:
                    value = credentials[config_key]
                    break
        if value:
            kwargs[param.name] = value

    # Handle graphql config if present
    if hasattr(entry, 'graphql_config') and entry.graphql_config:
        kwargs["endpoint"] = entry.graphql_config["endpoint"]
        kwargs["resources"] = entry.graphql_config["resources"]
        if "auth_prefix" in entry.graphql_config:
            kwargs["auth_prefix"] = entry.graphql_config["auth_prefix"]

    # Resource selection for verified sources
    print(f"  Using dlt source: {entry.import_path}", file=sys.stderr)
    source = source_func(**kwargs)

    if resource_names and hasattr(source, "with_resources"):
        source = source.with_resources(*resource_names)

    return source


def extract_metadata(
    source_type: str, credentials: dict[str, str], tables: list[str]
) -> dict[str, dict[str, dict[str, str]]]:
    """Extract column metadata from the source API."""
    entry = get_source_entry(source_type)

    if entry and entry.metadata_openapi_url:
        if source_type == "stripe":
            from dinobase.sync.metadata import extract_stripe_metadata
            return extract_stripe_metadata(credentials.get("api_key", ""), tables)

    if source_type == "hubspot":
        from dinobase.sync.metadata import extract_hubspot_metadata
        api_key = credentials.get("api_key", "")
        if api_key:
            return extract_hubspot_metadata(api_key, tables)

    if source_type in ("postgres", "mysql"):
        from dinobase.sync.metadata import extract_postgres_metadata
        conn_str = credentials.get("connection_string", credentials.get("credentials", ""))
        schema = credentials.get("schema", "public")
        if conn_str:
            return extract_postgres_metadata(conn_str, schema, tables)

    return {}
