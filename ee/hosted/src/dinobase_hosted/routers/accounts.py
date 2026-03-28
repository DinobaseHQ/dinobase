# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Account endpoints — login, token exchange, user info."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from supabase import create_client

from dinobase_hosted.auth import User, get_current_user
from dinobase_hosted.config import get_supabase_url, get_supabase_publishable_key, get_base_url
from dinobase_hosted.db import get_or_create_profile, get_profile, list_user_sources
from dinobase_hosted.models import (
    TokenExchangeRequest,
    RefreshTokenRequest,
    UserInfo,
)
from dinobase_hosted.storage import ensure_user_storage


router = APIRouter(tags=["accounts"])


@router.get("/login")
async def login(redirect_uri: str, state: str):
    """Redirect to Supabase hosted login page.

    After authentication, Supabase redirects back to `redirect_uri` with a code.
    The CLI callback server receives this and calls POST /token to exchange it.
    """
    supabase_url = get_supabase_url()
    params = {
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
    }
    # Supabase Auth uses PKCE flow via its hosted UI
    auth_url = f"{supabase_url}/auth/v1/authorize?{urlencode(params)}"
    return RedirectResponse(auth_url, status_code=302)


@router.post("/token")
async def exchange_token(body: TokenExchangeRequest):
    """Exchange a Supabase auth code for access + refresh tokens.

    Creates the user profile and allocates storage on first login.
    """
    supabase = create_client(get_supabase_url(), get_supabase_publishable_key())

    try:
        resp = supabase.auth.exchange_code_for_session({"auth_code": body.code})
    except Exception as e:
        raise HTTPException(400, f"Token exchange failed: {e}")

    session = resp.session
    user = resp.user

    if not session or not user:
        raise HTTPException(400, "No session returned from Supabase")

    # Ensure user has a profile and storage
    storage_url = ensure_user_storage(user.id)

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
        "user": {
            "id": user.id,
            "email": user.email,
            "storage_url": storage_url,
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshTokenRequest):
    """Refresh an expired session token."""
    supabase = create_client(get_supabase_url(), get_supabase_publishable_key())

    try:
        resp = supabase.auth.refresh_session(body.refresh_token)
    except Exception as e:
        raise HTTPException(400, f"Token refresh failed: {e}")

    session = resp.session
    if not session:
        raise HTTPException(400, "No session returned from Supabase")

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> UserInfo:
    """Get current user info."""
    profile = get_profile(user.id)
    if not profile:
        # Auto-create profile on first /me call
        storage_url = ensure_user_storage(user.id)
        profile = {"storage_url": storage_url, "plan": "free"}

    sources = list_user_sources(user.id)

    return UserInfo(
        id=user.id,
        email=user.email,
        plan=profile.get("plan", "free"),
        storage_url=profile["storage_url"],
        sources_count=len(sources),
    )
