"""Live fetch client — calls source APIs for single records using YAML configs.

When synced data is stale and the agent queries a single record by primary key,
this client calls the source API directly (e.g., GET /contacts/123) and returns
fresh data. Falls back gracefully on any error.
"""

from __future__ import annotations

import json
import ssl
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dinobase.sync.source_config import (
    build_client_auth_headers,
    get_client_base_url,
    get_client_headers,
    get_resource,
    get_resource_primary_key,
    load_source_config,
)


class LiveFetchClient:
    """Fetches single records from source APIs using YAML configs or registry configs."""

    def __init__(self, source_type: str, credentials: dict[str, str]):
        self.source_type = source_type
        self.credentials = credentials
        self.config = load_source_config(source_type)

        # Fall back to registry's live_fetch_config for dlt verified sources
        if self.config is None:
            from dinobase.sync.registry import get_source_entry
            entry = get_source_entry(source_type)
            if entry and entry.live_fetch_config:
                self.config = entry.live_fetch_config

    @property
    def available(self) -> bool:
        """Whether this source has a YAML config with resources."""
        return self.config is not None and bool(self.config.get("resources"))

    def can_fetch(self, table_name: str) -> bool:
        """Whether a specific table supports single-record fetch."""
        if not self.available:
            return False
        resource = get_resource(self.config, table_name)
        return resource is not None

    def fetch_by_id(
        self, table_name: str, record_id: str
    ) -> dict[str, Any] | None:
        """Fetch a single record by ID from the source API.

        Returns the parsed JSON response, or None on any error.
        """
        if not self.config:
            return None

        resource = get_resource(self.config, table_name)
        if resource is None:
            return None

        # Build URL: {base_url}/{resource_path}/{id}
        base_url = get_client_base_url(self.config, self.credentials)
        if not base_url:
            return None

        resource_path = resource.get("endpoint", {}).get("path", table_name)
        url = f"{base_url}/{resource_path.strip('/')}/{record_id}"

        # Build headers
        headers = get_client_headers(self.config, self.credentials)
        auth_headers = build_client_auth_headers(self.config, self.credentials)
        headers.update(auth_headers)
        headers["User-Agent"] = "dinobase/0.1"
        headers["Accept"] = "application/json"

        print(f"[live-fetch] GET {url}", file=sys.stderr)

        try:
            req = Request(url, headers=headers, method="GET")
            ctx = ssl.create_default_context()
            with urlopen(req, timeout=15, context=ctx) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except (HTTPError, URLError, json.JSONDecodeError, Exception) as e:
            print(f"[live-fetch] failed: {e}", file=sys.stderr)
            return None
