"""Configuration management for Dinobase."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import yaml


DEFAULT_DIR = Path.home() / ".dinobase"
CONFIG_FILE = "config.yaml"
DB_FILE = "dinobase.duckdb"
CLOUD_CREDENTIALS_FILE = "credentials.json"
DEFAULT_CLOUD_API_URL = "https://api.dinobase.ai"


def get_dinobase_dir() -> Path:
    return Path(os.environ.get("DINOBASE_DIR", DEFAULT_DIR))


def get_config_path() -> Path:
    return get_dinobase_dir() / CONFIG_FILE


def get_db_path() -> Path | str:
    if is_cloud_storage():
        return ":memory:"
    return get_dinobase_dir() / DB_FILE


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
        return {"sources": {}}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {"sources": {}}
    except yaml.YAMLError as e:
        import click
        click.echo(f"Error: broken config file at {path}", err=True)
        click.echo(f"YAML parse error: {e}", err=True)
        click.echo("Fix the file manually or delete it and run `dinobase init`.", err=True)
        raise SystemExit(1)


def source_exists(name: str) -> bool:
    """Check if a source with this name is already configured."""
    return name in load_config().get("sources", {})


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
    config_path = get_config_path()
    if not config_path.exists():
        config: dict[str, Any] = {"sources": {}}
        if storage_url:
            config["storage"] = {"url": _normalize_url(storage_url)}
        save_config(config)
    elif storage_url:
        # Update existing config with storage URL
        config = load_config()
        config["storage"] = {"url": _normalize_url(storage_url)}
        save_config(config)
    return ddir


def add_source(
    name: str,
    source_type: str,
    credentials: dict[str, str],
    sync_interval: str | None = None,
    freshness_threshold: str | None = None,
) -> None:
    config = load_config()
    source_config: dict[str, Any] = {
        "type": source_type,
        "credentials": credentials,
    }
    if sync_interval:
        source_config["sync_interval"] = sync_interval
    if freshness_threshold:
        source_config["freshness_threshold"] = freshness_threshold
    config["sources"][name] = source_config
    save_config(config)


def update_credentials(name: str, credentials: dict[str, str]) -> None:
    """Update the credentials for an existing source (e.g. after token refresh)."""
    config = load_config()
    if name in config["sources"]:
        config["sources"][name]["credentials"] = credentials
        save_config(config)


def get_oauth_proxy_url() -> str | None:
    """Return the configured OAuth proxy URL, or None."""
    return load_config().get("oauth_proxy_url")


def set_oauth_proxy_url(url: str) -> None:
    """Set the OAuth proxy URL in config."""
    config = load_config()
    config["oauth_proxy_url"] = url
    save_config(config)


def remove_source(name: str) -> None:
    config = load_config()
    config["sources"].pop(name, None)
    save_config(config)


def get_sources() -> dict[str, Any]:
    return load_config().get("sources", {})


# ---------------------------------------------------------------------------
# Freshness thresholds
# ---------------------------------------------------------------------------

# Defaults by source category (when not explicitly set in config)
_DEFAULT_THRESHOLDS: dict[str, str] = {
    "saas": "1h",
    "database": "6h",
    "cloud_storage": "6h",
}


def _parse_duration(duration: str) -> int:
    """Parse a human duration string (e.g., '1h', '30m', '6h') into seconds."""
    duration = duration.strip().lower()
    if duration.endswith("h"):
        return int(duration[:-1]) * 3600
    if duration.endswith("m"):
        return int(duration[:-1]) * 60
    if duration.endswith("s"):
        return int(duration[:-1])
    if duration.endswith("d"):
        return int(duration[:-1]) * 86400
    return int(duration)


def _source_category(source_type: str) -> str:
    """Classify a source type into a category for default thresholds."""
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


def get_freshness_threshold(source_name: str) -> int | None:
    """Return the freshness threshold in seconds for a source.

    Returns None for file sources (never stale).
    Uses explicit config value if set, otherwise defaults by source category.
    """
    sources = get_sources()
    source_config = sources.get(source_name, {})
    source_type = source_config.get("type", source_name)

    # File sources are never stale (they read live at query time)
    if _source_category(source_type) == "file":
        return None

    # Explicit threshold in config
    explicit = source_config.get("freshness_threshold")
    if explicit:
        return _parse_duration(explicit)

    # Default by category
    category = _source_category(source_type)
    default = _DEFAULT_THRESHOLDS.get(category)
    if default:
        return _parse_duration(default)

    return _parse_duration("1h")


# ---------------------------------------------------------------------------
# Cloud credentials (Dinobase Cloud account)
# ---------------------------------------------------------------------------


def _cloud_credentials_path() -> Path:
    # Cloud credentials are global to the CLI user, not per-workspace.
    # Always resolve against the home-based default dir so that setting
    # DINOBASE_DIR to a per-user cloud workspace (as the hosted service
    # worker does) doesn't break credential lookup in long-running processes
    # like the MCP server.
    base = Path(os.environ.get("DINOBASE_CREDENTIALS_DIR", DEFAULT_DIR))
    return base / CLOUD_CREDENTIALS_FILE


def is_cloud_logged_in() -> bool:
    """Check if the user has cloud credentials (token may be refreshable)."""
    creds = load_cloud_credentials()
    if not creds or not creds.get("access_token"):
        return False
    # Token expired with no refresh token — nothing we can do
    expires_at = creds.get("expires_at", 0)
    if expires_at and time.time() > expires_at and not creds.get("refresh_token"):
        return False
    return True


def ensure_fresh_cloud_token() -> str | None:
    """Return a valid cloud access_token, refreshing if expired.

    Returns None if no credentials exist.
    On refresh failure, returns the existing (stale) token — the API call
    will fail with 401 rather than silently falling back to local mode.
    """
    creds = load_cloud_credentials()
    if not creds:
        return None

    access_token = creds.get("access_token")
    if not access_token:
        return None

    expires_at = creds.get("expires_at", 0)
    if not expires_at or time.time() < expires_at - 60:
        return access_token  # still valid

    refresh_token = creds.get("refresh_token", "")
    if not refresh_token:
        return access_token  # no refresh token, return stale

    api_url = (creds.get("api_url") or get_cloud_api_url()).rstrip("/")

    try:
        from urllib.request import Request, urlopen
        req = Request(
            f"{api_url}/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": refresh_token}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            new_tokens = json.loads(resp.read())

        creds["access_token"] = new_tokens["access_token"]
        creds["refresh_token"] = new_tokens.get("refresh_token", refresh_token)
        creds["expires_at"] = new_tokens.get("expires_at", expires_at)
        save_cloud_credentials(creds)
        return creds["access_token"]
    except Exception:
        return access_token  # refresh failed; caller will get a 401


def load_cloud_credentials() -> dict[str, Any] | None:
    """Load cloud credentials from disk."""
    path = _cloud_credentials_path()
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_cloud_credentials(credentials: dict[str, Any]) -> None:
    """Save cloud credentials to disk."""
    path = _cloud_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(credentials, f, indent=2)
    # Restrict permissions to owner only
    path.chmod(0o600)


def clear_cloud_credentials() -> None:
    """Delete cloud credentials from disk."""
    path = _cloud_credentials_path()
    if path.exists():
        path.unlink()


def get_cloud_api_url() -> str:
    """Return the cloud API URL."""
    return os.environ.get("DINOBASE_CLOUD_URL", DEFAULT_CLOUD_API_URL)


def is_auto_annotate_enabled() -> bool:
    """Return True unless DINOBASE_AUTO_ANNOTATE=false (case-insensitive)."""
    val = os.environ.get("DINOBASE_AUTO_ANNOTATE", "true").strip().lower()
    return val not in ("false", "0", "no", "off")
