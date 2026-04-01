# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""JWT verification for Supabase Auth.

Uses the JWKS endpoint to auto-discover signing keys.
Supports both legacy HS256 and new ECC (ES256/P-256) keys.

Use `get_current_user` as a FastAPI dependency to protect endpoints.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import Header, HTTPException
from jose import jwt, JWTError

from dinobase_hosted.config import get_supabase_url


class User:
    """Authenticated user extracted from a Supabase JWT."""

    __slots__ = ("id", "email")

    def __init__(self, user_id: str, email: str):
        self.id = user_id
        self.email = email


# ---------------------------------------------------------------------------
# JWKS cache — refresh every 5 minutes
# ---------------------------------------------------------------------------

_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0
_JWKS_TTL = 300  # seconds


def _get_jwks() -> dict[str, Any]:
    """Fetch JWKS from Supabase, with caching."""
    global _jwks_cache, _jwks_fetched_at

    if _jwks_cache and (time.time() - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache

    url = f"{get_supabase_url()}/auth/v1/.well-known/jwks.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_fetched_at = time.time()
    return _jwks_cache


def _decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a Supabase JWT using JWKS."""
    jwks = _get_jwks()

    # Try decoding with all keys in the JWKS
    # Supabase may have current + previous keys during rotation
    errors = []
    for key in jwks.get("keys", []):
        alg = key.get("alg", "ES256")
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[alg],
                options={"verify_aud": False},
            )
        except JWTError as e:
            errors.append(str(e))
            continue

    raise JWTError(f"No matching key found in JWKS. Tried {len(errors)} key(s): {'; '.join(errors)}")


async def get_current_user(authorization: str = Header()) -> User:
    """FastAPI dependency — verify the Bearer token and return the user."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")

    token = authorization[7:]  # strip "Bearer "
    try:
        payload = _decode_token(token)
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")

    user_id = payload.get("sub")
    email = payload.get("email", "")

    if not user_id:
        raise HTTPException(401, "Token missing subject claim")

    return User(user_id=user_id, email=email)
