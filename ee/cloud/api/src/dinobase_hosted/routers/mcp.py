# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Remote MCP endpoint over streamable-HTTP.

Mounts a FastMCP server at /mcp that Claude.ai Custom Connectors and any
other MCP-over-HTTP client can consume. Each request is authenticated via
the existing Supabase Bearer JWT; tools resolve to the authenticated user's
data context using the same `_get_user_engine` path as the REST endpoints.

Mounted in `query` mode (where the engine has direct data access). In
`web` mode, app.py proxies /mcp/* to the query service over httpx,
including SSE streams.
"""

from __future__ import annotations

import contextvars
from typing import Any

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from dinobase_hosted.auth import User, get_current_user
from dinobase_hosted.routers.query import _get_user_engine


_current_user: contextvars.ContextVar["User | None"] = contextvars.ContextVar(
    "_dinobase_mcp_user", default=None
)


def _user() -> User:
    user = _current_user.get()
    if user is None:
        raise RuntimeError("MCP tool invoked without authenticated user context")
    return user


mcp_server = FastMCP(
    "dinobase",
    instructions=(
        "Dinobase: agent-first SQL layer over your synced data sources. "
        "Use `info` first to see available sources and their tables; then "
        "`list_tables` for the schema tree, `describe` for column-level "
        "detail and sample rows, and `query` to run SELECT statements."
    ),
)


@mcp_server.tool()
def info() -> str:
    """Database overview: connected sources, tables, and how to query them."""
    engine, _db = _get_user_engine(_user())
    from dinobase.mcp.server import _build_instructions
    return _build_instructions(engine)


@mcp_server.tool()
def list_tables() -> dict[str, Any]:
    """Structured tree of schemas and tables available to query."""
    engine, _db = _get_user_engine(_user())
    return engine.list_sources()


@mcp_server.tool()
def describe(table: str) -> dict[str, Any]:
    """Describe a table: columns, types, annotations, sample rows.

    Args:
        table: fully-qualified table name (e.g. "posthog.events").
    """
    engine, _db = _get_user_engine(_user())
    return engine.describe_table(table)


@mcp_server.tool()
def query(sql: str, max_rows: int = 200) -> dict[str, Any]:
    """Execute a SELECT against the user's data. Read-only.

    Args:
        sql: a single SELECT statement.
        max_rows: cap on rows returned (default 200, max 10_000).
    """
    capped = max(1, min(int(max_rows), 10_000))
    engine, _db = _get_user_engine(_user())
    return engine.execute(sql, max_rows=capped)


class _BearerAuthMiddleware:
    """ASGI wrapper: validate the Supabase Bearer JWT, bind User to a ContextVar."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        try:
            user = await get_current_user(authorization=auth)
        except HTTPException as exc:
            response = JSONResponse({"error": exc.detail}, status_code=exc.status_code)
            await response(scope, receive, send)
            return

        token = _current_user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user.reset(token)


# Public ASGI app to mount in app.py (mounted at /mcp in query mode).
mcp_app = _BearerAuthMiddleware(mcp_server.streamable_http_app())
