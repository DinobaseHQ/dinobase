"""HTTP client for the Dinobase Cloud API."""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


DEFAULT_API_URL = "https://api.dinobase.ai"


class CloudClient:
    """Thin client for the Dinobase Cloud API."""

    def __init__(self, api_url: str, access_token: str):
        self.api_url = api_url.rstrip("/")
        self.access_token = access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.api_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, headers=self._headers(), method=method)

        try:
            with urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            error_body = e.read().decode()
            try:
                detail = json.loads(error_body).get("detail", error_body)
            except (json.JSONDecodeError, AttributeError):
                detail = error_body
            raise RuntimeError(f"Cloud API error ({e.code}): {detail}") from e
        except URLError as e:
            raise RuntimeError(f"Failed to reach Dinobase Cloud at {url}: {e}") from e

    # -- Accounts --

    def whoami(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/auth/me")

    # -- Sources --

    def list_sources(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/sources/")  # type: ignore[return-value]

    def add_source(
        self, name: str, source_type: str, credentials: dict[str, str], sync_interval: str = "1h"
    ) -> dict[str, Any]:
        return self._request("POST", "/api/v1/sources/", {
            "name": name,
            "type": source_type,
            "credentials": credentials,
            "sync_interval": sync_interval,
        })

    def start_oauth(self, source_name: str, redirect_uri: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/sources/{source_name}/auth?redirect_uri={redirect_uri}",
        )

    def complete_oauth(
        self, source_name: str, code: str, redirect_uri: str, state: str
    ) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/sources/{source_name}/auth/callback", {
            "code": code,
            "redirect_uri": redirect_uri,
            "state": state,
        })

    def delete_source(self, source_name: str) -> dict[str, Any]:
        return self._request("DELETE", f"/api/v1/sources/{source_name}")

    # -- Sync --

    def trigger_sync(self, source_name: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/v1/sync/", {
            "source_name": source_name,
        })

    def sync_status(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/sync/status")  # type: ignore[return-value]

    def get_sync_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/sync/jobs/{job_id}")

    # -- Query --

    def query(self, sql: str, max_rows: int = 200) -> dict[str, Any]:
        return self._request("POST", "/api/v1/query/", {
            "sql": sql,
            "max_rows": max_rows,
        })

    def describe(self, table: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/query/describe/{table}")

    def info(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/query/info")

    def confirm(self, mutation_id: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/query/", {
            "sql": f"CONFIRM {mutation_id}",
        })

    def cancel(self, mutation_id: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/query/", {
            "sql": f"CANCEL {mutation_id}",
        })
