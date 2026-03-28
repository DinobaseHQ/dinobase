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
    delete_user_source,
    get_latest_sync_jobs,
)
from dinobase_hosted.encryption import encrypt_credentials, decrypt_credentials
from dinobase_hosted.models import AddSourceRequest, SourceOAuthCallbackRequest
from dinobase_hosted.oauth.providers import PROVIDERS


router = APIRouter(tags=["sources"])


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
            "last_sync": job["finished_at"] if job else None,
            "last_sync_status": job["status"] if job else None,
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
    encrypted = encrypt_credentials(body.credentials)
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


@router.delete("/{source_name}")
async def remove_source(
    source_name: str,
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Remove a source and its data."""
    deleted = delete_user_source(user.id, source_name)
    if not deleted:
        raise HTTPException(404, f"Source '{source_name}' not found")
    # TODO: also delete S3 data for this source
    return {"deleted": True}
