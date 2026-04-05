# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Source management endpoints — add, list, OAuth connect, delete."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException

from dinobase_hosted.auth import User, get_current_user
from dinobase_hosted.config import get_base_url
from dinobase_hosted.db import (
    list_user_sources,
    get_user_source,
    upsert_user_source,
    rename_user_source,
    delete_user_source,
    get_latest_sync_jobs,
    get_profile,
)
from dinobase_hosted.encryption import encrypt_credentials, decrypt_credentials
from dinobase_hosted.models import AddSourceRequest, RenameSourceRequest, SourceOAuthCallbackRequest
from dinobase_hosted.oauth.config import get_provider_credentials
from dinobase_hosted.oauth.providers import PROVIDERS


router = APIRouter(tags=["sources"])


@router.get("/registry")
async def source_registry(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return all available sources with their credential schemas, categorized."""
    from dinobase.sync.registry import SOURCES

    def _category(import_path: str) -> str:
        if "sql_database" in import_path:
            return "database"
        if "filesystem" in import_path:
            return "file_storage"
        return "api"

    sources = []
    for entry in sorted(SOURCES.values(), key=lambda e: e.name):
        data = entry.to_dict()
        data["category"] = _category(entry.import_path)
        data["oauth_configured"] = (
            entry.name in PROVIDERS and get_provider_credentials(entry.name) is not None
        )
        sources.append(data)

    return {"sources": sources}


@router.get("/")
async def list_sources(user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List all connected sources for the current user."""
    sources = list_user_sources(user.id)
    jobs = {j["source_name"]: j for j in get_latest_sync_jobs(user.id)}

    result = []
    for src in sources:
        job = jobs.get(src["source_name"])
        result.append({
            "name": src["source_name"],
            "type": src["source_type"],
            "auth_method": src["auth_method"],
            "sync_interval": src.get("sync_interval", "1h"),
            "updated_at": src.get("updated_at"),
            "last_sync": job["finished_at"] if job else None,
            "last_sync_status": job["status"] if job else None,
            "last_sync_error": job["error_message"] if job else None,
            "last_job_id": job["id"] if job else None,
            "tables_synced": job["tables_synced"] if job else 0,
            "rows_synced": job["rows_synced"] if job else 0,
        })
    return result


@router.post("/")
async def add_source(
    body: AddSourceRequest,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Add a source with API key credentials."""
    credentials = body.credentials

    # On update, keep existing values for any blank fields so users don't
    # have to re-enter credentials they haven't changed.
    if any(v == "" for v in credentials.values()):
        existing = get_user_source(user.id, body.name)
        if existing:
            existing_creds = decrypt_credentials(existing["credentials_encrypted"])
            credentials = {**existing_creds, **{k: v for k, v in credentials.items() if v}}

    encrypted = encrypt_credentials(credentials)
    upsert_user_source(
        user_id=user.id,
        source_name=body.name,
        source_type=body.type,
        auth_method="api_key",
        credentials_encrypted=encrypted,
        sync_interval=body.sync_interval,
    )
    return {"name": body.name, "type": body.type, "status": "added"}


@router.post("/{source_name}/auth")
async def start_oauth(
    source_name: str,
    redirect_uri: str,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Start OAuth flow for a source.

    Returns the auth URL that the user/agent should open in a browser.
    After the user authorizes, the provider redirects back to the CLI's
    local callback, which then calls /auth/callback to complete the flow.
    """
    # Determine the source type (default to source_name if not specified)
    source_type = source_name

    if source_type not in PROVIDERS:
        raise HTTPException(
            400,
            f"Source '{source_type}' does not support OAuth. "
            f"Available OAuth sources: {', '.join(sorted(PROVIDERS.keys()))}",
        )

    state = secrets.token_urlsafe(32)
    base_url = get_base_url()

    # The OAuth flow goes through our OAuth router
    auth_url = f"{base_url}/oauth/auth/{source_type}?" + urlencode({
        "redirect_uri": redirect_uri,
        "state": state,
    })

    return {"auth_url": auth_url, "state": state}


@router.post("/{source_name}/auth/callback")
async def complete_oauth(
    source_name: str,
    body: SourceOAuthCallbackRequest,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Complete the OAuth flow — exchange the code for tokens and store them."""
    source_type = source_name
    base_url = get_base_url()

    # Exchange the code for tokens via the OAuth router
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/oauth/token/{source_type}",
            json={"code": body.code, "redirect_uri": body.redirect_uri},
        )

    if resp.status_code >= 400:
        raise HTTPException(502, f"OAuth token exchange failed: {resp.text}")

    tokens = resp.json()

    # Store encrypted credentials
    credentials = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_in": tokens.get("expires_in", 0),
        "auth_method": "oauth",
    }
    encrypted = encrypt_credentials(credentials)

    upsert_user_source(
        user_id=user.id,
        source_name=source_name,
        source_type=source_type,
        auth_method="oauth",
        credentials_encrypted=encrypted,
    )

    return {"name": source_name, "type": source_type, "status": "connected"}


@router.patch("/{source_name}/rename")
async def rename_source(
    source_name: str,
    body: RenameSourceRequest,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Rename a source, preserving its credentials and sync history."""
    new_name = body.new_name.strip()
    if not new_name:
        raise HTTPException(400, "new_name cannot be empty")
    if new_name == source_name:
        return {"name": source_name}
    found = rename_user_source(user.id, source_name, new_name)
    if not found:
        raise HTTPException(404, f"Source '{source_name}' not found")
    return {"name": new_name}


@router.delete("/{source_name}")
async def remove_source(
    source_name: str,
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Remove a source and its data."""
    deleted = delete_user_source(user.id, source_name)
    if not deleted:
        raise HTTPException(404, f"Source '{source_name}' not found")

    # Delete the source's cloud storage data (best-effort)
    profile = get_profile(user.id)
    if profile and profile.get("storage_url"):
        try:
            from dinobase.cloud import CloudStorage
            cloud = CloudStorage(profile["storage_url"])
            data_path = cloud._to_fs_path(f"{cloud.storage_url}data/{source_name}")
            cloud.fs.rm(data_path, recursive=True)
        except Exception as e:
            import sys
            print(
                f"[dinobase] Warning: failed to delete cloud data for source "
                f"'{source_name}': {e}",
                file=sys.stderr,
            )

    return {"deleted": True}
