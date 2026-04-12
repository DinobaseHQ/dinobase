"""Dinobase MCP client — sync Python API for calling MCP server tools.

Usage:
    from dinobase.mcp import call, tools, servers, search, instructions

    result = call("posthog_mcp.dashboards-get-all")
    result = call("posthog_mcp.dashboard-get", id=1118504)
    all_tools = tools("posthog_mcp")
    matching = search("dashboard")
    info = instructions("posthog_mcp")
    svrs = servers()
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import yaml

from dinobase.config import get_connectors_dir


def call(ref: str, **kwargs: Any) -> dict[str, Any]:
    """Call an MCP tool.

    Args:
        ref: 'server.tool' format (e.g. 'posthog_mcp.dashboards-get-all')
        **kwargs: Tool arguments passed as keyword args.

    Returns:
        Raw tool result with 'content', optional 'structuredContent' and 'isError'.
    """
    from dinobase.fetch.mcp_connector import call_tool

    if "." not in ref:
        raise ValueError(f"Use server.tool format (e.g. my_server.list_files), got: {ref!r}")
    server, tool_name = ref.split(".", 1)
    return asyncio.run(call_tool(server, tool_name, kwargs or None))


def tools(server: str) -> list[dict[str, Any]]:
    """List all tools on an MCP server with full schemas."""
    from dinobase.fetch.mcp_connector import list_all_tools

    return asyncio.run(list_all_tools(server))


def servers() -> list[dict[str, Any]]:
    """List all connected MCP servers with tool counts."""
    from dinobase.fetch.mcp_connector import list_all_tools

    connectors_dir = get_connectors_dir()
    if not connectors_dir.is_dir():
        return []

    results = []
    for path in sorted(connectors_dir.glob("*.yaml")):
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            if not cfg or "transport" not in cfg:
                continue
        except Exception:
            continue

        name = cfg["name"]
        transport = cfg["transport"]
        entry: dict[str, Any] = {
            "name": name,
            "description": cfg.get("description", ""),
            "transport": transport["type"],
        }

        try:
            tool_list = asyncio.run(list_all_tools(name))
            entry["tools"] = len(tool_list)
            entry["tool_names"] = [t["name"] for t in tool_list]
        except Exception as e:
            entry["tools"] = 0
            entry["error"] = str(e)

        results.append(entry)

    return results


def search(pattern: str) -> list[dict[str, Any]]:
    """Regex search tool names/descriptions across all MCP servers."""
    from dinobase.fetch.mcp_connector import list_all_tools

    regex = re.compile(pattern, re.IGNORECASE)

    connectors_dir = get_connectors_dir()
    if not connectors_dir.is_dir():
        return []

    matches = []
    for path in sorted(connectors_dir.glob("*.yaml")):
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            if not cfg or "transport" not in cfg:
                continue
        except Exception:
            continue

        name = cfg["name"]
        try:
            tool_list = asyncio.run(list_all_tools(name))
        except Exception:
            continue

        for t in tool_list:
            text = t["name"] + " " + (t.get("description") or "")
            if regex.search(text):
                matches.append({
                    "server": name,
                    "tool": t["name"],
                    "description": t.get("description", ""),
                })

    return matches


def instructions(server: str) -> dict[str, Any]:
    """Get server info and usage instructions."""
    from dinobase.fetch.mcp_connector import get_server_info

    return asyncio.run(get_server_info(server))
