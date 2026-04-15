# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""OAuth proxy router.

Implements the contract expected by the Dinobase CLI and setup-ui:
  GET  /auth/{provider}?redirect_uri=...&state=...[&subdomain=...]   -> 302 to provider
  GET  /callback/{provider}?code=...&state=...                       -> 302 to client
  POST /token/{provider}  {code, ctx}                                 -> {access_token, ...}
  POST /refresh/{provider} {refresh_token}                            -> {access_token, ...}
  GET  /providers                                                     -> [{name, scopes}, ...]

Only the proxy's own `/callback/{provider}` URL is registered with OAuth
providers. The client's local callback URL (e.g. `http://localhost:47382/callback`,
which uses an ephemeral port) is sealed into the `state` parameter and unwrapped
when the provider redirects back, so every provider app only needs a single
stable redirect URI registration.

PKCE: for providers with `requires_pkce=True`, the proxy generates the
code_verifier itself and seals it into the opaque state blob. The same blob
round-trips back through the client as `ctx` and the verifier is retrieved
at /token time. The client never sees the verifier in cleartext.

Tenant-subdomain providers (Shopify, Zendesk, WooCommerce): the caller passes
`subdomain=...` to /auth; the proxy substitutes it into the provider's
authorization_url and token_url, and seals the value into state so the same
substitution can be applied at /token time.

The routes live on an APIRouter so they can be mounted into any FastAPI app:
  app.include_router(oauth_router, prefix="/oauth")
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from dinobase_hosted.config import get_base_url, get_encryption_key
from dinobase_hosted.oauth.config import get_provider_credentials
from dinobase_hosted.oauth.providers import PROVIDERS


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    code: str
    # Opaque, proxy-signed blob returned alongside the code in the /callback
    # redirect. Carries the PKCE code_verifier and any tenant subdomain so the
    # proxy can complete the token exchange statelessly. Optional only so that
    # non-PKCE providers keep working for older clients.
    ctx: str | None = None
    # Deprecated — ignored by the server. Older clients may still send it.
    redirect_uri: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
    # Required for tenant-subdomain providers (Shopify, Zendesk, WooCommerce)
    # so the proxy can reconstruct the correct token URL.
    subdomain: str | None = None


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


def _proxy_callback_url(provider_name: str) -> str:
    """The stable redirect URI registered with the OAuth provider."""
    return f"{get_base_url()}/oauth/callback/{provider_name}"


def _fernet() -> Fernet:
    return Fernet(get_encryption_key().encode())


def _gen_pkce() -> tuple[str, str]:
    """Return (verifier, S256 challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(64)[:96]  # 43..128 chars
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _substitute_subdomain(url: str, placeholder: str | None, subdomain: str | None) -> str:
    """Fill in `{placeholder}` in a provider URL with the tenant subdomain."""
    if not placeholder:
        return url
    if not subdomain:
        raise HTTPException(400, f"This provider requires a `subdomain` parameter")
    if not subdomain.replace("-", "").replace(".", "").isalnum():
        raise HTTPException(400, "Invalid subdomain: must be alphanumeric")
    return url.replace("{" + placeholder + "}", subdomain)


def _seal_state(
    provider: str,
    client_redirect_uri: str,
    client_state: str,
    code_verifier: str | None = None,
    subdomain: str | None = None,
) -> str:
    """Encrypt the client + PKCE + tenant context into an opaque state token."""
    parsed = urlparse(client_redirect_uri)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "redirect_uri must be http(s)")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise HTTPException(400, "http redirect_uri only allowed for localhost")

    payload: dict[str, str] = {
        "p": provider,
        "ru": client_redirect_uri,
        "cs": client_state,
    }
    if code_verifier:
        payload["cv"] = code_verifier
    if subdomain:
        payload["sd"] = subdomain

    token = _fernet().encrypt(json.dumps(payload).encode())
    return base64.urlsafe_b64encode(token).rstrip(b"=").decode()


def _unseal_state(provider: str, sealed: str) -> dict[str, str]:
    """Return the sealed payload dict or raise 400."""
    try:
        padding = b"=" * (-len(sealed) % 4)
        token = base64.urlsafe_b64decode(sealed.encode() + padding)
        payload = json.loads(_fernet().decrypt(token))
    except (InvalidToken, ValueError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid or expired OAuth state")

    if payload.get("p") != provider:
        raise HTTPException(400, "OAuth state provider mismatch")
    return payload


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["oauth"])


@router.get("/auth/{provider_name}")
async def authorize(
    provider_name: str,
    redirect_uri: str,
    state: str,
    subdomain: str | None = None,
):
    """Start the OAuth flow -- redirects the user's browser to the provider.

    The provider only sees the proxy's own callback URL. The client's local
    `redirect_uri` (typically `http://localhost:<ephemeral>/callback`) is sealed
    into the state parameter and unwrapped in `/callback/{provider}`.

    For PKCE providers, a code_verifier is generated server-side and also sealed
    into state. For tenant-subdomain providers, the caller must pass `subdomain`.
    """
    provider = _get_provider(provider_name)
    creds = _get_credentials(provider_name)

    authorization_url = _substitute_subdomain(
        provider.authorization_url, provider.subdomain_placeholder, subdomain,
    )

    code_verifier: str | None = None
    code_challenge: str | None = None
    if provider.requires_pkce:
        code_verifier, code_challenge = _gen_pkce()

    sealed_state = _seal_state(
        provider_name, redirect_uri, state,
        code_verifier=code_verifier,
        subdomain=subdomain,
    )

    params: dict[str, str] = {
        "client_id": creds.client_id,
        "redirect_uri": _proxy_callback_url(provider_name),
        "state": sealed_state,
        "response_type": "code",
    }

    if provider.scopes:
        params["scope"] = " ".join(provider.scopes)

    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    params.update(provider.extra_authorize_params)

    url = f"{authorization_url}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


@router.get("/callback/{provider_name}")
async def callback(provider_name: str, code: str | None = None,
                   state: str | None = None, error: str | None = None,
                   error_description: str | None = None):
    """Receive the provider's redirect, then 302 back to the client's local URL.

    This is the only URL that needs to be registered with each OAuth provider.
    The sealed state blob is passed through to the client as `ctx` so it can be
    handed back to /token for PKCE verification without leaking the verifier.
    """
    if not state:
        raise HTTPException(400, "Missing state parameter")

    _get_provider(provider_name)  # 404 early if the provider name is bogus
    payload = _unseal_state(provider_name, state)
    client_redirect_uri = payload["ru"]
    client_state = payload["cs"]

    forward_params: dict[str, str] = {"state": client_state, "ctx": state}
    if error:
        forward_params["error"] = error
        if error_description:
            forward_params["error_description"] = error_description
    elif code:
        forward_params["code"] = code
    else:
        raise HTTPException(400, "Callback missing both code and error")

    separator = "&" if urlparse(client_redirect_uri).query else "?"
    url = f"{client_redirect_uri}{separator}{urlencode(forward_params)}"
    return RedirectResponse(url, status_code=302)


@router.post("/token/{provider_name}")
async def exchange_token(provider_name: str, body: TokenRequest):
    """Exchange an authorization code for access + refresh tokens.

    The client must pass back `ctx` (the opaque blob received in the /callback
    redirect) for PKCE or subdomain providers. The legacy `redirect_uri` field
    in the body is ignored — the proxy always uses its own callback URL so it
    matches what was sent to the provider during /auth.
    """
    provider = _get_provider(provider_name)
    creds = _get_credentials(provider_name)

    code_verifier: str | None = None
    subdomain: str | None = None
    if body.ctx:
        payload = _unseal_state(provider_name, body.ctx)
        code_verifier = payload.get("cv")
        subdomain = payload.get("sd")

    if provider.requires_pkce and not code_verifier:
        raise HTTPException(400, f"{provider_name} requires PKCE — missing ctx")
    if provider.subdomain_placeholder and not subdomain:
        raise HTTPException(400, f"{provider_name} requires subdomain — missing ctx")

    token_url = _substitute_subdomain(
        provider.token_url, provider.subdomain_placeholder, subdomain,
    )

    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": body.code,
        "redirect_uri": _proxy_callback_url(provider_name),
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
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

    token_url = _substitute_subdomain(
        provider.token_url, provider.subdomain_placeholder, body.subdomain,
    )

    data = {
        "grant_type": "refresh_token",
        "refresh_token": body.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
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
