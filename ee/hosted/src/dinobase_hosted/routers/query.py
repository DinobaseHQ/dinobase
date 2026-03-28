# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Query endpoints — SQL execution against user's cloud data."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dinobase_hosted.auth import User, get_current_user
from dinobase_hosted.db import get_profile
from dinobase_hosted.models import QueryRequest


router = APIRouter(tags=["query"])


def _get_user_engine(user: User):
    """Create a QueryEngine pointing at the user's cloud storage."""
    profile = get_profile(user.id)
    if not profile:
        raise HTTPException(400, "No user profile found. Run `dinobase login` first.")

    storage_url = profile["storage_url"]

    # Set the storage URL so DinobaseDB picks up cloud mode
    os.environ["DINOBASE_STORAGE_URL"] = storage_url

    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    db = DinobaseDB()
    return QueryEngine(db), db


@router.post("/")
async def execute_query(
    body: QueryRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute SQL against the user's cloud data."""
    engine, db = _get_user_engine(user)
    try:
        result = engine.execute(body.sql, max_rows=body.max_rows)
        return result
    finally:
        db.close()


@router.get("/describe/{table}")
async def describe_table(
    table: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Describe a table's columns, types, and sample data."""
    engine, db = _get_user_engine(user)
    try:
        return engine.describe_table(table)
    finally:
        db.close()


@router.get("/info")
async def info(user: User = Depends(get_current_user)) -> dict[str, str]:
    """Get database overview (same as `dinobase info`)."""
    engine, db = _get_user_engine(user)
    try:
        from dinobase.mcp.server import _build_instructions
        instructions = _build_instructions(engine)
        return {"instructions": instructions}
    finally:
        db.close()
