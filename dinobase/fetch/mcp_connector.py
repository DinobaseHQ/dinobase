"""MCP connector fetcher — fetches data from MCP server reading tools.

Connects to an MCP server (stdio, SSE, or streamable HTTP), discovers
read-only tools, calls them, and caches results as JSON files exposed
as DuckDB views via read_json_auto(). Same downstream as LocalConnectorFetcher.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dinobase.db import DinobaseDB

# Tool name prefixes that indicate read-only operations
_READ_PREFIXES = ("list_", "get_", "search_", "read_", "fetch_")
# Tool name prefixes that indicate mutating operations
_WRITE_PREFIXES = ("create_", "update_", "delete_", "set_", "send_", "remove_", "put_")


def _is_reading_tool(tool: Any, allowlist: list[str] | None = None) -> bool:
    """Classify whether an MCP tool is safe to call for data fetching.

    Priority:
    1. User allowlist (tools: in YAML) — exact match
    2. MCP ToolAnnotations — readOnlyHint / destructiveHint
    3. Name heuristics — prefix matching
    4. Skip tools with required parameters (can't call without context)
    """
    name = tool.name

    # 1. User allowlist
    if allowlist is not None:
        return name in allowlist

    # 2. ToolAnnotations
    ann = tool.annotations
    if ann is not None:
        if getattr(ann, "destructiveHint", False):
            return False
        if getattr(ann, "readOnlyHint", False):
            # Still check for required params
            return not _has_required_params(tool)

    # 3. Name heuristics
    name_lower = name.lower()
    if any(name_lower.startswith(p) for p in _WRITE_PREFIXES):
        return False
    if not any(name_lower.startswith(p) for p in _READ_PREFIXES):
        return False

    # 4. Required params filter
    return not _has_required_params(tool)


def _has_required_params(tool: Any) -> bool:
    """Check if a tool has required input parameters."""
    schema = tool.inputSchema or {}
    required = schema.get("required", [])
    return len(required) > 0


def _extract_rows(result: Any) -> list[dict[str, Any]]:
    """Extract tabular data from a CallToolResult.

    Tries structuredContent first, then parses TextContent as JSON,
    falls back to a single (content TEXT) row.
    """
    # Try structuredContent
    if result.structuredContent is not None:
        data = result.structuredContent
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]

    # Try parsing text content as JSON
    for block in result.content or []:
        if block.type == "text" and block.text:
            text = block.text.strip()
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    return [parsed]
            except (json.JSONDecodeError, ValueError):
                pass
            # Not JSON — return as single text row
            return [{"content": text}]

    return []


class MCPConnectorFetcher:
    """Fetches data from an MCP server's reading tools."""

    def __init__(self, db: DinobaseDB, source_name: str):
        from dinobase.fetch.connector import ConnectorError, load_local_connector_config

        self.db = db
        self.source_name = source_name
        self.config = load_local_connector_config(source_name)
        if self.config is None:
            raise ConnectorError(
                f"No connector config found: '{source_name}'.\n"
                f"Create one with: dinobase connector create {source_name}"
            )

        self._transport_config = self.config["transport"]
        self._allowlist = self.config.get("tools")
        self._cached_resources: list[str] | None = None

    @property
    def mode(self) -> str:
        from dinobase.fetch.connector import get_connector_mode
        return get_connector_mode(self.config)

    @property
    def resources(self) -> list[str]:
        if self._cached_resources is None:
            self._cached_resources = asyncio.run(self._discover_tools())
        return self._cached_resources

    def fetch_resource(self, resource_name: str) -> Path:
        """Fetch data from a single MCP tool, write to JSON cache, create view."""
        return asyncio.run(self._fetch_resource_async(resource_name))

    def fetch_all(self) -> dict[str, Path]:
        """Fetch all reading tools in a single MCP session."""
        return asyncio.run(self._fetch_all_async())

    def is_fresh(self, resource_name: str, threshold_seconds: int | None = None) -> bool:
        """Check if cached data is still fresh based on file mtime."""
        from dinobase.config import get_cache_dir, get_freshness_threshold

        cache_path = get_cache_dir() / self.source_name / f"{resource_name}.json"
        if not cache_path.exists():
            return False

        if threshold_seconds is None:
            threshold_seconds = get_freshness_threshold(self.source_name)
            if threshold_seconds is None:
                threshold_seconds = 3600

        age = time.time() - cache_path.stat().st_mtime
        return age < threshold_seconds

    # -- async internals --

    async def _get_session(self):
        """Create the appropriate MCP transport context manager."""
        t = self._transport_config
        transport_type = t["type"]

        if transport_type == "stdio":
            from mcp.client.stdio import StdioServerParameters, stdio_client
            params = StdioServerParameters(
                command=t["command"],
                args=t.get("args", []),
                env=t.get("env"),
            )
            return stdio_client(params)
        elif transport_type == "sse":
            from mcp.client.sse import sse_client
            return sse_client(url=t["url"], headers=t.get("headers"))
        elif transport_type == "streamable_http":
            from mcp.client.streamable_http import streamablehttp_client
            return streamablehttp_client(url=t["url"], headers=t.get("headers"))
        else:
            from dinobase.fetch.connector import ConnectorError
            raise ConnectorError(
                f"Unknown MCP transport type: '{transport_type}'.\n"
                f"Supported: stdio, sse, streamable_http"
            )

    async def _discover_tools(self) -> list[str]:
        """Connect to MCP server and discover reading tools."""
        from mcp import ClientSession

        transport_cm = await self._get_session()
        async with transport_cm as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = [
                    t.name for t in result.tools
                    if _is_reading_tool(t, self._allowlist)
                ]
                return tools

    async def _fetch_resource_async(self, resource_name: str) -> Path:
        """Fetch a single tool's data via MCP."""
        from mcp import ClientSession

        print(
            f"  [mcp] fetching {self.source_name}.{resource_name}...",
            file=sys.stderr,
        )

        transport_cm = await self._get_session()
        async with transport_cm as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(resource_name, {})

                if result.isError:
                    from dinobase.fetch.connector import ConnectorError
                    error_text = ""
                    for block in result.content or []:
                        if block.type == "text":
                            error_text += block.text
                    raise ConnectorError(
                        f"MCP tool '{resource_name}' returned an error: {error_text}"
                    )

                rows = _extract_rows(result)

        return self._write_cache_and_view(resource_name, rows)

    async def _fetch_all_async(self) -> dict[str, Path]:
        """Fetch all reading tools in a single MCP connection."""
        from mcp import ClientSession

        transport_cm = await self._get_session()
        results: dict[str, Path] = {}

        async with transport_cm as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Discover tools
                tool_list = await session.list_tools()
                reading_tools = [
                    t.name for t in tool_list.tools
                    if _is_reading_tool(t, self._allowlist)
                ]
                self._cached_resources = reading_tools

                for tool_name in reading_tools:
                    print(
                        f"  [mcp] fetching {self.source_name}.{tool_name}...",
                        file=sys.stderr,
                    )
                    try:
                        result = await session.call_tool(tool_name, {})
                        if result.isError:
                            error_text = ""
                            for block in result.content or []:
                                if block.type == "text":
                                    error_text += block.text
                            print(
                                f"  [mcp] warning: {tool_name} returned error: {error_text}",
                                file=sys.stderr,
                            )
                            continue
                        rows = _extract_rows(result)
                        results[tool_name] = self._write_cache_and_view(tool_name, rows)
                    except Exception as e:
                        print(
                            f"  [mcp] warning: failed to fetch {tool_name}: {e}",
                            file=sys.stderr,
                        )

        return results

    def _write_cache_and_view(self, resource_name: str, rows: list[dict[str, Any]]) -> Path:
        """Write rows to JSON cache and create a DuckDB view."""
        from dinobase.config import get_cache_dir
        from dinobase.db import META_SCHEMA

        cache_dir = get_cache_dir() / self.source_name
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{resource_name}.json"

        with open(cache_path, "w") as f:
            json.dump(rows, f, default=str)

        print(
            f"  [mcp] cached {len(rows)} rows → {cache_path}",
            file=sys.stderr,
        )

        # Create DuckDB view
        conn = self.db.conn
        schema = self.source_name
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        conn.execute(
            f'CREATE OR REPLACE VIEW "{schema}"."{resource_name}" AS '
            f"SELECT * FROM read_json_auto('{cache_path}')"
        )

        # Update metadata
        conn.execute(
            f"""INSERT OR REPLACE INTO {META_SCHEMA}.tables
                (source_name, schema_name, table_name, row_count, last_sync)
                VALUES (?, ?, ?, ?, current_timestamp)""",
            [self.source_name, schema, resource_name, len(rows)],
        )

        return cache_path
