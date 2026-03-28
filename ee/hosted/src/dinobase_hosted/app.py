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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dinobase_hosted.oauth.router import router as oauth_router
from dinobase_hosted.routers import accounts, sources, sync, query
from dinobase_hosted.config import get_allowed_origins

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

# OAuth proxy endpoints (existing, backward-compatible)
app.include_router(oauth_router, prefix="/oauth")

# Cloud API endpoints
app.include_router(accounts.router, prefix="/api/v1/auth")
app.include_router(sources.router, prefix="/api/v1/sources")
app.include_router(sync.router, prefix="/api/v1/sync")
app.include_router(query.router, prefix="/api/v1/query")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "dinobase-cloud"}
