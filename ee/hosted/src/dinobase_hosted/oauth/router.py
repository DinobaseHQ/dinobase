# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""OAuth proxy router.

Implements the contract expected by `dinobase auth`:
  GET  /auth/{provider}?redirect_uri=...&state=...   -> 302 to provider
  POST /token/{provider}  {code, redirect_uri}        -> {access_token, ...}
  POST /refresh/{provider} {refresh_token}             -> {access_token, ...}
  GET  /providers                                      -> [{name, scopes}, ...]

The routes live on an APIRouter so they can be mounted into any FastAPI app:
  app.include_router(oauth_router, prefix="/oauth")
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dinobase_hosted.oauth.config import get_provider_credentials
from dinobase_hosted.oauth.providers import PROVIDERS


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    code: str
    redirect_uri: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_provider(name: str):
    provider = PROVIDERS.get(name)
    if not provider:
        raise HTTPException(404, f"Unknown provider: {name}")
    return provider


def _get_credentials(name: str):
    creds = get_provider_credentials(name)
    if not creds:
        raise HTTPException(
            501,
            f"Provider '{name}' is not configured. "
            f"Set DINOBASE_OAUTH_{name.upper()}_CLIENT_ID and "
            f"DINOBASE_OAUTH_{name.upper()}_CLIENT_SECRET.",
        )
    return creds


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["oauth"])


@router.get("/auth/{provider_name}")
async def authorize(provider_name: str, redirect_uri: str, state: str):
    """Start the OAuth flow -- redirects the user's browser to the provider."""
    provider = _get_provider(provider_name)
    creds = _get_credentials(provider_name)

    params = {
        "client_id": creds.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
    }

    if provider.scopes:
        params["scope"] = " ".join(provider.scopes)

    params.update(provider.extra_authorize_params)

    from fastapi.responses import RedirectResponse
    url = f"{provider.authorization_url}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


@router.post("/token/{provider_name}")
async def exchange_token(provider_name: str, body: TokenRequest):
    """Exchange an authorization code for access + refresh tokens."""
    provider = _get_provider(provider_name)
    creds = _get_credentials(provider_name)

    data = {
        "grant_type": "authorization_code",
        "code": body.code,
        "redirect_uri": body.redirect_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            provider.token_url,
            data=data,
            headers={"Accept": "application/json"},
        )

    if resp.status_code >= 400:
        raise HTTPException(
            502,
            f"Token exchange failed ({resp.status_code}): {resp.text}",
        )

    token_data = resp.json()

    return {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_in": token_data.get("expires_in", 0),
        "token_type": token_data.get("token_type", "Bearer"),
    }


@router.post("/refresh/{provider_name}")
async def refresh_token(provider_name: str, body: RefreshRequest):
    """Refresh an expired access token."""
    provider = _get_provider(provider_name)
    creds = _get_credentials(provider_name)

    data = {
        "grant_type": "refresh_token",
        "refresh_token": body.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            provider.token_url,
            data=data,
            headers={"Accept": "application/json"},
        )

    if resp.status_code >= 400:
        raise HTTPException(
            502,
            f"Token refresh failed ({resp.status_code}): {resp.text}",
        )

    token_data = resp.json()

    result = {
        "access_token": token_data.get("access_token", ""),
        "expires_in": token_data.get("expires_in", 0),
        "token_type": token_data.get("token_type", "Bearer"),
    }

    # Some providers rotate refresh tokens
    if "refresh_token" in token_data:
        result["refresh_token"] = token_data["refresh_token"]

    return result


@router.get("/providers")
async def list_providers():
    """List all supported OAuth providers and their configured status."""
    result = []
    for name, provider in sorted(PROVIDERS.items()):
        creds = get_provider_credentials(name)
        result.append({
            "name": name,
            "scopes": provider.scopes,
            "configured": creds is not None,
        })
    return result


@router.get("/health")
async def health():
    return {"status": "ok"}
