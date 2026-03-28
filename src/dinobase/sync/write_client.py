"""Generic write client — executes write-back to source APIs using YAML configs.

Reads the source's YAML config to find write endpoints, constructs the
correct HTTP request (auth, URL, body), and executes it.

Used by the mutation engine after a mutation is confirmed.
"""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from dinobase.sync.source_config import (
    load_source_config,
    get_write_endpoints,
    get_endpoint,
    build_auth_headers,
    build_request_body,
    build_url,
)


class WriteClient:
    """Executes writes against source APIs using YAML-defined endpoints."""

    def __init__(self, source_name: str, credentials: dict[str, str]):
        self.source_name = source_name
        self.credentials = credentials
        self.config = load_source_config(source_name)

    @property
    def has_config(self) -> bool:
        return self.config is not None

    @property
    def write_endpoints(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        return get_write_endpoints(self.config)

    def list_write_operations(self) -> list[dict[str, str]]:
        """List available write operations for this source."""
        return [
            {
                "name": ep["name"],
                "description": ep.get("description", ""),
                "method": ep.get("method", "POST"),
                "path": ep.get("path", ""),
            }
            for ep in self.write_endpoints
        ]

    def execute(
        self,
        endpoint_name: str,
        data: dict[str, Any],
        path_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a write operation against the source API.

        Args:
            endpoint_name: Name of the write endpoint (e.g., "identify", "create_annotation")
            data: Request body data
            path_params: URL path parameters (e.g., {"event_type": "purchase"})

        Returns: {"status": "ok", "response": ...} or {"error": ...}
        """
        if not self.config:
            return {"error": f"No YAML config found for source '{self.source_name}'"}

        endpoint = get_endpoint(self.config, endpoint_name)
        if endpoint is None:
            available = [ep["name"] for ep in self.write_endpoints]
            return {
                "error": f"Write endpoint '{endpoint_name}' not found for {self.source_name}",
                "available_endpoints": available,
            }

        if not endpoint.get("write", False):
            return {"error": f"Endpoint '{endpoint_name}' is a read endpoint, not a write endpoint"}

        # Build the request
        url = build_url(endpoint, path_params)
        method = endpoint.get("method", "POST").upper()
        headers = build_auth_headers(endpoint, self.credentials)
        headers["Content-Type"] = "application/json"
        headers["User-Agent"] = "dinobase/0.1"

        body = build_request_body(endpoint, self.credentials, data)

        print(
            f"[write] {method} {url} ({endpoint_name})",
            file=sys.stderr,
        )

        # Execute the request
        try:
            # For DELETE requests, skip body if empty (many APIs expect no body)
            req_data = None if method == "DELETE" and not body else json.dumps(body).encode("utf-8")
            req = Request(
                url,
                data=req_data,
                headers=headers,
                method=method,
            )

            import ssl
            ctx = ssl.create_default_context()
            try:
                with urlopen(req, timeout=30, context=ctx) as resp:
                    response_body = resp.read().decode("utf-8")
                    try:
                        response_data = json.loads(response_body)
                    except json.JSONDecodeError:
                        response_data = {"raw": response_body}

                    return {
                        "status": "ok",
                        "http_status": resp.status,
                        "response": response_data,
                    }
            except HTTPError as e:
                error_body = e.read().decode("utf-8") if e.fp else ""
                try:
                    error_data = json.loads(error_body)
                except (json.JSONDecodeError, ValueError):
                    error_data = {"raw": error_body}
                return {
                    "error": f"HTTP {e.code}: {e.reason}",
                    "http_status": e.code,
                    "response": error_data,
                }
        except URLError as e:
            return {"error": f"Connection failed: {e.reason}"}
        except Exception as e:
            return {"error": f"Request failed: {e}"}
