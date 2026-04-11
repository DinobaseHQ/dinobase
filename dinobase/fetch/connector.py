"""Local connector fetcher — fetches data from user-defined REST API connectors.

Uses dlt's rest_api_source for extraction (handles auth, pagination, incremental)
but skips the full dlt pipeline. Fetched data is cached as JSON files and exposed
as DuckDB views via read_json_auto().

Two modes:
- live: auto-fetch on first query or when cache is stale
- sync: fetch on explicit `dinobase sync/refresh` only
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError

import yaml

if TYPE_CHECKING:
    from dinobase.db import DinobaseDB


class ConnectorError(Exception):
    """User-facing error from a local connector with actionable guidance."""

    pass


def _classify_error(
    exc: Exception, source_name: str, resource_name: str
) -> str:
    """Translate a raw exception into an actionable error message."""
    exc_str = str(exc)
    exc_lower = exc_str.lower()

    # HTTP errors (from urllib or requests)
    if isinstance(exc, HTTPError) or "httperror" in type(exc).__name__.lower():
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code is None:
            # Try to extract from string
            import re as _re

            m = _re.search(r"(\d{3})", exc_str)
            code = int(m.group(1)) if m else 0

        if code in (401, 403):
            return (
                f"Authentication failed for '{source_name}' (HTTP {code}).\n"
                f"Check your API key: dinobase add {source_name} --api-key <value>"
            )
        if code == 404:
            return (
                f"Endpoint not found for '{source_name}.{resource_name}' (HTTP 404).\n"
                f"Check the endpoint path in your connector config: "
                f"dinobase connector edit {source_name}"
            )
        if code == 429:
            return (
                f"Rate limited by '{source_name}' (HTTP 429).\n"
                f"Wait a moment, then retry: dinobase refresh {source_name}"
            )
        if code and code >= 500:
            return (
                f"Server error from '{source_name}' (HTTP {code}).\n"
                f"The API may be temporarily down — retry later."
            )

    # Connection errors
    if "connectionerror" in type(exc).__name__.lower() or "urlerror" in type(exc).__name__.lower():
        # Try to extract hostname
        host_match = re.search(r"host[= ]*'?([^\s'\",:]+)", exc_lower)
        host = host_match.group(1) if host_match else "the API"
        return (
            f"Cannot connect to {host}.\n"
            f"Check the base_url in your connector config: "
            f"dinobase connector edit {source_name}"
        )

    if "timeout" in exc_lower:
        return (
            f"Request timed out for '{source_name}.{resource_name}'.\n"
            f"The API may be slow — retry later: dinobase refresh {source_name}"
        )

    # Auth-related strings in generic errors
    if "401" in exc_str or "403" in exc_str or "unauthorized" in exc_lower or "forbidden" in exc_lower:
        return (
            f"Authentication failed for '{source_name}'.\n"
            f"Check your API key: dinobase add {source_name} --api-key <value>"
        )

    if "404" in exc_str and "not found" in exc_lower:
        return (
            f"Endpoint not found for '{source_name}.{resource_name}'.\n"
            f"Check the endpoint path: dinobase connector edit {source_name}"
        )

    # Check nested/wrapped exceptions (dlt wraps errors in PipelineStepFailed etc.)
    if "resolve" in exc_lower or "nodename" in exc_lower or "name resolution" in exc_lower:
        host_match = re.search(r"host='([^']+)'", exc_str)
        host = host_match.group(1) if host_match else "the API"
        return (
            f"Cannot connect to {host}.\n"
            f"Check the base_url in your connector config: "
            f"dinobase connector edit {source_name}"
        )

    if "max retries exceeded" in exc_lower or "connection refused" in exc_lower:
        host_match = re.search(r"host='([^']+)'", exc_str)
        host = host_match.group(1) if host_match else "the API"
        return (
            f"Cannot connect to {host}.\n"
            f"Check the base_url in your connector config, "
            f"or verify your network connection."
        )

    # Fallback
    return f"Fetch failed for '{source_name}.{resource_name}': {exc}"


def is_local_connector(source_name: str) -> bool:
    """Check if source_name has a YAML config in the local connectors dir."""
    from dinobase.config import get_connectors_dir

    return (get_connectors_dir() / f"{source_name}.yaml").exists()


def load_local_connector_config(source_name: str) -> dict[str, Any] | None:
    """Load a local connector YAML config by name."""
    from dinobase.config import get_connectors_dir

    path = get_connectors_dir() / f"{source_name}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def get_connector_mode(config: dict[str, Any]) -> str:
    """Determine the fetch mode for a connector.

    Returns 'live', 'sync', or resolves 'auto':
    - auto → live if no paginator defined, sync if paginator present.
    """
    mode = config.get("mode", "auto")
    if mode != "auto":
        return mode
    # Auto-detect: if a paginator is configured, default to sync
    paginator = config.get("client", {}).get("paginator")
    if paginator and paginator.get("type") not in (None, "single_page"):
        return "sync"
    return "live"


class LocalConnectorFetcher:
    """Fetches data from a local connector via dlt iteration + JSON caching."""

    def __init__(self, db: DinobaseDB, source_name: str):
        self.db = db
        self.source_name = source_name
        self.config = load_local_connector_config(source_name)
        if self.config is None:
            raise ConnectorError(
                f"No local connector config found: '{source_name}'.\n"
                f"Create one with: dinobase connector create {source_name}"
            )

        # Load credentials from user config
        from dinobase.config import get_sources

        sources = get_sources()
        source_cfg = sources.get(source_name, {})
        self.credentials = source_cfg.get("credentials", {})
        self.source_type = self.config.get("name", source_name)

    @property
    def mode(self) -> str:
        return get_connector_mode(self.config)

    @property
    def resources(self) -> list[str]:
        """List of resource names defined in the connector."""
        return [r["name"] for r in self.config.get("resources", [])]

    def _validate_before_fetch(self) -> None:
        """Check credentials and config before making HTTP calls."""
        # Check credentials exist in config.yaml
        if not self.credentials:
            cred_names = [c["name"] for c in self.config.get("credentials", [])]
            flags = " ".join(
                f"--{c.replace('_', '-')} <value>" for c in cred_names
            )
            raise ConnectorError(
                f"No credentials configured for '{self.source_name}'.\n"
                f"Run: dinobase add {self.source_name} {flags}"
            )

        # Check all placeholders have values
        base_url = self.config.get("client", {}).get("base_url", "")
        auth_token = self.config.get("client", {}).get("auth", {}).get("token", "")
        template = base_url + auth_token
        for resource in self.config.get("resources", []):
            template += resource.get("endpoint", {}).get("path", "")

        placeholders = set(re.findall(r"\{(\w+)\}", template))
        missing = placeholders - set(self.credentials.keys())
        if missing:
            flags = " ".join(
                f"--{c.replace('_', '-')} <value>" for c in sorted(missing)
            )
            raise ConnectorError(
                f"Missing credentials for '{self.source_name}': "
                f"{', '.join(sorted(missing))}.\n"
                f"Run: dinobase add {self.source_name} {flags}"
            )

    def fetch_resource(self, resource_name: str) -> Path:
        """Fetch all records for one resource via dlt, write to JSON cache.

        Returns path to the cache file.
        Raises ConnectorError with actionable guidance on failure.
        """
        from dinobase.config import get_cache_dir
        from dinobase.sync.yaml_source import build_dlt_source

        self._validate_before_fetch()

        print(
            f"  [connector] fetching {self.source_name}.{resource_name}...",
            file=sys.stderr,
        )

        # Build dlt source — handles auth, pagination, credential substitution
        try:
            source = build_dlt_source(
                self.source_type, self.credentials, [resource_name]
            )
        except Exception as e:
            raise ConnectorError(
                f"Invalid connector config for '{self.source_name}': {e}\n"
                f"Check your config: dinobase connector edit {self.source_name}"
            ) from e

        # Iterate the dlt source directly to collect all records
        rows: list[dict[str, Any]] = []
        try:
            for resource_obj in source.resources.values():
                for item in resource_obj:
                    if isinstance(item, dict):
                        rows.append(item)
                    elif isinstance(item, list):
                        rows.extend(item)
        except Exception as e:
            raise ConnectorError(
                _classify_error(e, self.source_name, resource_name)
            ) from e

        # Write to cache file
        cache_dir = get_cache_dir() / self.source_name
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{resource_name}.json"
        with open(cache_path, "w") as f:
            json.dump(rows, f, default=str)

        print(
            f"  [connector] cached {len(rows)} rows → {cache_path}",
            file=sys.stderr,
        )

        # Create DuckDB view
        self._create_view(resource_name, cache_path, len(rows))
        return cache_path

    def fetch_all(self) -> dict[str, Path]:
        """Fetch all resources. Returns {resource_name: cache_path}."""
        results = {}
        for name in self.resources:
            results[name] = self.fetch_resource(name)
        return results

    def is_fresh(self, resource_name: str, threshold_seconds: int | None = None) -> bool:
        """Check if cached data is still fresh based on file mtime."""
        from dinobase.config import get_cache_dir, get_freshness_threshold

        cache_path = get_cache_dir() / self.source_name / f"{resource_name}.json"
        if not cache_path.exists():
            return False

        if threshold_seconds is None:
            threshold_seconds = get_freshness_threshold(self.source_name)
            if threshold_seconds is None:
                threshold_seconds = 3600  # default 1h

        age = time.time() - cache_path.stat().st_mtime
        return age < threshold_seconds

    def _create_view(
        self, resource_name: str, cache_path: Path, row_count: int
    ) -> None:
        """Create a DuckDB view over the cached JSON file."""
        conn = self.db.conn
        schema = self.source_name

        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        conn.execute(
            f'CREATE OR REPLACE VIEW "{schema}"."{resource_name}" AS '
            f"SELECT * FROM read_json_auto('{cache_path}')"
        )

        # Update metadata
        from dinobase.db import META_SCHEMA

        conn.execute(
            f"""INSERT OR REPLACE INTO {META_SCHEMA}.tables
                (source_name, schema_name, table_name, row_count, last_sync)
                VALUES (?, ?, ?, ?, current_timestamp)""",
            [self.source_name, schema, resource_name, row_count],
        )


def register_cached_views(db: DinobaseDB) -> None:
    """Create DuckDB views for any existing JSON cache files.

    Called on DB init to restore views from previous sessions.
    """
    from dinobase.config import get_cache_dir

    cache_dir = get_cache_dir()
    if not cache_dir.is_dir():
        return

    for source_dir in cache_dir.iterdir():
        if not source_dir.is_dir():
            continue
        schema = source_dir.name
        json_files = list(source_dir.glob("*.json"))
        if not json_files:
            continue

        db.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        for json_file in json_files:
            table = json_file.stem
            try:
                db.conn.execute(
                    f'CREATE OR REPLACE VIEW "{schema}"."{table}" AS '
                    f"SELECT * FROM read_json_auto('{json_file}')"
                )
            except Exception as e:
                print(
                    f"  [connector] warning: could not create view "
                    f"{schema}.{table}: {e}",
                    file=sys.stderr,
                )
