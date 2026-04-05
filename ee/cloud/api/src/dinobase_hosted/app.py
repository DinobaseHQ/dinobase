# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Dinobase Cloud API — the hosted service.

Pure API server. The web frontend lives in ee/web/ (Next.js).

Routers:
- /oauth/*          — OAuth proxy (provider auth flows)
- /api/v1/auth/*    — User accounts (login, token exchange, profile)
- /api/v1/sources/* — Source management (add, list, OAuth connect, delete)
- /api/v1/sync/*    — Sync management (trigger, status, jobs)
- /api/v1/query/*   — SQL query execution against user's cloud data
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dinobase_hosted.oauth.router import router as oauth_router
from dinobase_hosted.routers import accounts, sources, sync, query, sandbox
from dinobase_hosted.config import get_allowed_origins

# ---------------------------------------------------------------------------
# Deployment mode — controls which routers are mounted.
#
#   all     (default)  All routers. Good for local dev and simple self-hosted.
#   web                OAuth + accounts + sources + sync + proxy→query.
#   query              Query + sandbox only. Internal; no OAuth exposed.
#   worker             No HTTP routes. cli.py starts a sync worker loop instead.
#
# In production, run behind a load balancer:
#   DINOBASE_MODE=web    → web-facing server (auth, sources, sync HTTP API)
#   DINOBASE_MODE=query  → SQL compute pool (scales independently)
#   DINOBASE_MODE=worker → sync worker process (polls Supabase for pending jobs)
# ---------------------------------------------------------------------------
_MODE = os.environ.get("DINOBASE_MODE", "all")
if _MODE not in ("all", "web", "query", "worker"):
    raise RuntimeError(
        f"Unknown DINOBASE_MODE={_MODE!r}. Must be 'all', 'web', 'query', or 'worker'."
    )

app = FastAPI(
    title="Dinobase Cloud API",
    description="Hosted Dinobase service — OAuth, sync, and query.",
    version="0.1.0",
)

# CORS — allow the web frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth and account/source/sync management — web-facing only.
# Query and worker processes are internal; they don't expose auth endpoints.
if _MODE in ("all", "web"):
    app.include_router(oauth_router,    prefix="/oauth")
    app.include_router(accounts.router, prefix="/api/v1/auth")
    app.include_router(sources.router,  prefix="/api/v1/sources")
    app.include_router(sync.router,     prefix="/api/v1/sync")

# SQL query execution and AI sandbox — compute-heavy, separate process.
if _MODE in ("all", "query"):
    app.include_router(query.router,   prefix="/api/v1/query")
    app.include_router(sandbox.router, prefix="/api/v1/sandbox")

# web mode: proxy query/sandbox traffic to the query server so the client
# only needs one URL. Activates when DINOBASE_QUERY_URL is set.
if _MODE == "web":
    import httpx
    from fastapi import Request
    from fastapi.responses import Response as _Resp, StreamingResponse as _SSEResp

    _QUERY_URL = (os.environ.get("DINOBASE_QUERY_URL") or "").rstrip("/")

    if _QUERY_URL:
        async def _forward(request: Request, target: str, timeout: float) -> "_Resp":
            headers = {
                k: v for k, v in request.headers.items()
                if k.lower() not in ("host", "content-length")
            }
            body = await request.body()
            params = dict(request.query_params)

            client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
            try:
                req = client.build_request(
                    method=request.method,
                    url=target,
                    headers=headers,
                    content=body,
                    params=params,
                )
                upstream = await client.send(req, stream=True)
            except Exception:
                await client.aclose()
                raise
            resp_headers = {
                k: v for k, v in upstream.headers.multi_items()
                if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")
            }
            content_type = upstream.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                async def _sse():
                    try:
                        async for chunk in upstream.aiter_bytes():
                            yield chunk
                    finally:
                        await upstream.aclose()
                        await client.aclose()
                return _SSEResp(
                    _sse(), status_code=upstream.status_code,
                    headers=resp_headers, media_type="text/event-stream",
                )

            try:
                data = await upstream.aread()
            finally:
                await upstream.aclose()
                await client.aclose()
            return _Resp(
                content=data, status_code=upstream.status_code,
                headers=resp_headers, media_type=content_type or None,
            )

        @app.api_route("/api/v1/query/{path:path}", methods=["GET", "POST"])
        async def _proxy_query(path: str, request: Request):
            return await _forward(request, f"{_QUERY_URL}/api/v1/query/{path}", timeout=300.0)

        @app.api_route("/api/v1/sandbox/{path:path}", methods=["GET", "POST"])
        async def _proxy_sandbox(path: str, request: Request):
            return await _forward(request, f"{_QUERY_URL}/api/v1/sandbox/{path}", timeout=600.0)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "dinobase-cloud", "mode": _MODE}
