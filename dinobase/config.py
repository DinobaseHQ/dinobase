"""Configuration management for Dinobase."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_DIR = Path.home() / ".dinobase"
CONFIG_FILE = "config.yaml"
DB_FILE = "dinobase.duckdb"


def get_dinobase_dir() -> Path:
    return Path(os.environ.get("DINOBASE_DIR", DEFAULT_DIR))


def get_config_path() -> Path:
    return get_dinobase_dir() / CONFIG_FILE


def get_db_path() -> Path | str:
    if is_cloud_storage():
        return ":memory:"
    return get_dinobase_dir() / DB_FILE


def get_connectors_dir() -> Path:
    """Directory for user-defined local connector YAML configs."""
    return get_dinobase_dir() / "connectors"


def get_cache_dir() -> Path:
    """Directory for cached JSON data from local connectors."""
    return get_dinobase_dir() / "cache"


def get_verified_sources_cache_dir() -> Path:
    """Directory for on-demand-fetched dlt verified sources."""
    return get_dinobase_dir() / "cache" / "verified-sources"


# ---------------------------------------------------------------------------
# Cloud storage
# ---------------------------------------------------------------------------


def get_storage_config() -> dict[str, Any]:
    """Return storage configuration.

    Resolves from (highest priority first):
    1. DINOBASE_STORAGE_URL env var
    2. storage.url in config.yaml
    3. Default: local storage
    """
    # Env var takes priority
    env_url = os.environ.get("DINOBASE_STORAGE_URL")
    if env_url:
        return {"type": _storage_type_from_url(env_url), "url": _normalize_url(env_url)}

    # Config file
    config = load_config()
    storage = config.get("storage", {})
    url = storage.get("url")
    if url:
        return {"type": _storage_type_from_url(url), "url": _normalize_url(url)}

    return {"type": "local", "url": None}


def is_cloud_storage() -> bool:
    """Check if cloud storage is configured."""
    return get_storage_config()["type"] != "local"


def get_storage_url() -> str | None:
    """Return the cloud storage URL, or None for local mode."""
    return get_storage_config()["url"]


def _storage_type_from_url(url: str) -> str:
    """Determine storage type from URL protocol."""
    if url.startswith("s3://"):
        return "s3"
    if url.startswith("gs://"):
        return "gcs"
    if url.startswith("az://"):
        return "azure"
    return "local"


def _normalize_url(url: str) -> str:
    """Ensure storage URL ends with /."""
    return url if url.endswith("/") else url + "/"


def load_config() -> dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        return {"connectors": {}}
    try:
        with open(path) as f:
            config = yaml.safe_load(f) or {"connectors": {}}
    except yaml.YAMLError as e:
        import click
        click.echo(f"Error: broken config file at {path}", err=True)
        click.echo(f"YAML parse error: {e}", err=True)
        click.echo("Fix the file manually or delete it and run `dinobase init`.", err=True)
        raise SystemExit(1)

    # Migrate old `sources` key to `connectors`
    if "sources" in config and "connectors" not in config:
        import click
        click.echo(
            "Note: migrating config.yaml — renaming 'sources' key to 'connectors'.",
            err=True,
        )
        config["connectors"] = config.pop("sources")
        save_config(config)

    return config


def connector_exists(name: str) -> bool:
    """Check if a connector with this name is already configured."""
    return name in load_config().get("connectors", {})


# Backward-compat alias
source_exists = connector_exists


def save_config(config: dict[str, Any]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    # Restrict config file to owner only (contains API keys)
    path.chmod(0o600)


def init_dinobase(storage_url: str | None = None) -> Path:
    """Create the dinobase directory and default config. Returns the directory path.

    If storage_url is provided, saves it to config and uses cloud mode.
    """
    ddir = get_dinobase_dir()
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "connectors").mkdir(exist_ok=True)
    (ddir / "cache").mkdir(exist_ok=True)
    config_path = get_config_path()
    if not config_path.exists():
        config: dict[str, Any] = {"connectors": {}}
        if storage_url:
            config["storage"] = {"url": _normalize_url(storage_url)}
        save_config(config)
    elif storage_url:
        # Update existing config with storage URL
        config = load_config()
        config["storage"] = {"url": _normalize_url(storage_url)}
        save_config(config)
    return ddir


def add_connector(
    name: str,
    connector_type: str,
    credentials: dict[str, str],
    sync_interval: str | None = None,
    freshness_threshold: str | None = None,
    resources: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    config = load_config()
    connector_config: dict[str, Any] = {
        "type": connector_type,
        "credentials": credentials,
    }
    if sync_interval:
        connector_config["sync_interval"] = sync_interval
    if freshness_threshold:
        connector_config["freshness_threshold"] = freshness_threshold
    if resources:
        connector_config["resources"] = list(resources)
    if params:
        connector_config["params"] = dict(params)
    config["connectors"][name] = connector_config
    save_config(config)


# Backward-compat alias
def add_source(
    name: str,
    source_type: str,
    credentials: dict[str, str],
    sync_interval: str | None = None,
    freshness_threshold: str | None = None,
    resources: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    add_connector(
        name, source_type, credentials, sync_interval, freshness_threshold,
        resources=resources, params=params,
    )


def update_credentials(name: str, credentials: dict[str, str]) -> None:
    """Update the credentials for an existing connector (e.g. after token refresh)."""
    config = load_config()
    if name in config["connectors"]:
        config["connectors"][name]["credentials"] = credentials
        save_config(config)


def remove_connector(name: str) -> None:
    config = load_config()
    config["connectors"].pop(name, None)
    save_config(config)


# Backward-compat alias
remove_source = remove_connector


def get_connectors() -> dict[str, Any]:
    return load_config().get("connectors", {})


# Backward-compat alias
get_sources = get_connectors


# ---------------------------------------------------------------------------
# Freshness thresholds
# ---------------------------------------------------------------------------

# Defaults by connector category (when not explicitly set in config)
_DEFAULT_THRESHOLDS: dict[str, str] = {
    "saas": "1h",
    "database": "6h",
    "cloud_storage": "6h",
}


def _parse_duration(duration: str) -> int:
    """Parse a human duration string (e.g., '1h', '30m', '6h') into seconds."""
    original = duration
    duration = duration.strip().lower()
    try:
        if duration.endswith("h"):
            return int(duration[:-1]) * 3600
        if duration.endswith("m"):
            return int(duration[:-1]) * 60
        if duration.endswith("s"):
            return int(duration[:-1])
        if duration.endswith("d"):
            return int(duration[:-1]) * 86400
        return int(duration)
    except ValueError:
        raise ValueError(f"Invalid duration '{original}': expected a number followed by h, m, s, or d (e.g. '1h', '30m', '6h')")


def _source_category(source_type: str) -> str:
    """Classify a connector type into a category for default thresholds."""
    if source_type in ("parquet", "csv"):
        return "file"
    try:
        from dinobase.sync.registry import get_source_entry
        entry = get_source_entry(source_type)
        if entry:
            if "sql_database" in entry.import_path:
                return "database"
            if "filesystem" in entry.import_path:
                return "cloud_storage"
    except Exception:
        pass
    return "saas"


def get_freshness_threshold(connector_name: str) -> int | None:
    """Return the freshness threshold in seconds for a connector.

    Returns None for file connectors (never stale).
    Uses explicit config value if set, otherwise defaults by connector category.
    """
    connectors = get_connectors()
    connector_config = connectors.get(connector_name, {})
    connector_type = connector_config.get("type", connector_name)

    # File connectors are never stale (they read live at query time)
    if _source_category(connector_type) == "file":
        return None

    # Explicit threshold in config
    explicit = connector_config.get("freshness_threshold")
    if explicit:
        return _parse_duration(explicit)

    # Default by category
    category = _source_category(connector_type)
    default = _DEFAULT_THRESHOLDS.get(category)
    if default:
        return _parse_duration(default)

    return _parse_duration("1h")


def is_auto_annotate_enabled() -> bool:
    """Return True unless DINOBASE_AUTO_ANNOTATE=false (case-insensitive)."""
    val = os.environ.get("DINOBASE_AUTO_ANNOTATE", "true").strip().lower()
    return val not in ("false", "0", "no", "off")
