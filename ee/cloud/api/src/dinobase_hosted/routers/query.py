# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Query endpoints — SQL execution against user's cloud data."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dinobase_hosted.auth import User, get_current_user
from dinobase_hosted.db import get_profile
from dinobase_hosted.models import QueryRequest


router = APIRouter(tags=["query"])

# Per-process cache of DinobaseDB instances keyed by storage_url (or db_path).
# Avoids re-initialising in-memory DuckDB + re-scanning S3 on every request.
# Each entry expires after DB_CACHE_TTL seconds so that stale data is bounded
# even when multiple servers run behind a load balancer (no cross-server
# coordination; each server refreshes independently when the TTL expires).
DB_CACHE_TTL = int(os.environ.get("DINOBASE_DB_CACHE_TTL", "300"))  # default 5 min

_db_cache: dict[str, tuple["DinobaseDB", float]] = {}  # type: ignore[name-defined]


def invalidate_db_cache(storage_url: str) -> None:
    """Drop the cached DinobaseDB for a storage URL (e.g. after a local sync)."""
    entry = _db_cache.pop(storage_url, None)
    if entry is not None:
        try:
            entry[0].close()
        except Exception:
            pass


def _get_user_engine(user: User):
    """Return a QueryEngine pointing at the user's storage, reusing a cached DB."""
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    profile = get_profile(user.id)
    if profile:
        key = profile["storage_url"]
        db = DinobaseDB(storage_url=key)
        kwargs: dict = {"storage_url": key}
    else:
        local_root = os.environ.get("DINOBASE_LOCAL_STORAGE_ROOT")
        if local_root:
            user_dir = Path(local_root.rstrip("/")) / user.id
            user_dir.mkdir(parents=True, exist_ok=True)
            key = str(user_dir / "dinobase.duckdb")
            kwargs = {"db_path": user_dir / "dinobase.duckdb"}
        else:
            from dinobase.config import get_storage_config
            sc = get_storage_config()
            if sc["type"] == "local":
                raise HTTPException(
                    400,
                    "No cloud profile found. Run `dinobase login` or set DINOBASE_LOCAL_STORAGE_ROOT.",
                )
            key = sc["url"]
            kwargs = {"storage_url": key}

    now = time.monotonic()
    entry = _db_cache.get(key)
    if entry is None or now - entry[1] > DB_CACHE_TTL:
        # Cache miss or TTL expired — build a fresh DB and cache it
        if entry is not None:
            try:
                entry[0].close()
            except Exception:
                pass
        db = DinobaseDB(**kwargs)
        _db_cache[key] = (db, now)
    else:
        db = entry[0]

    return QueryEngine(db), db


@router.post("/")
async def execute_query(
    body: QueryRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute SQL against the user's cloud data."""
    engine, _db = _get_user_engine(user)
    return engine.execute(body.sql, max_rows=body.max_rows)


@router.get("/describe/{table}")
async def describe_table(
    table: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Describe a table's columns, types, and sample data."""
    engine, _db = _get_user_engine(user)
    return engine.describe_table(table)


@router.get("/info")
async def info(user: User = Depends(get_current_user)) -> dict[str, str]:
    """Get database overview (same as `dinobase info`)."""
    engine, _db = _get_user_engine(user)
    from dinobase.mcp.server import _build_instructions
    return {"instructions": _build_instructions(engine)}


@router.get("/tables")
async def list_tables(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return structured schema/table tree for the schema browser."""
    engine, _db = _get_user_engine(user)
    return engine.list_connectors()
