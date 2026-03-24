"""Configuration management for Dinobase."""

from __future__ import annotations

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


def get_db_path() -> Path:
    return get_dinobase_dir() / DB_FILE


def load_config() -> dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        return {"sources": {}}
    with open(path) as f:
        return yaml.safe_load(f) or {"sources": {}}


def save_config(config: dict[str, Any]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def init_dinobase() -> Path:
    """Create the dinobase directory and default config. Returns the directory path."""
    ddir = get_dinobase_dir()
    ddir.mkdir(parents=True, exist_ok=True)
    config_path = get_config_path()
    if not config_path.exists():
        save_config({"sources": {}})
    return ddir


def add_source(
    name: str,
    source_type: str,
    credentials: dict[str, str],
    sync_interval: str | None = None,
) -> None:
    config = load_config()
    source_config: dict[str, Any] = {
        "type": source_type,
        "credentials": credentials,
    }
    if sync_interval:
        source_config["sync_interval"] = sync_interval
    config["sources"][name] = source_config
    save_config(config)


def remove_source(name: str) -> None:
    config = load_config()
    config["sources"].pop(name, None)
    save_config(config)


def get_sources() -> dict[str, Any]:
    return load_config().get("sources", {})
