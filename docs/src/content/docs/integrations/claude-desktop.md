---
title: Claude Desktop
description: Connect Dinobase to Claude Desktop so Claude can query your business data directly.
---

Dinobase integrates with [Claude Desktop](https://claude.ai/download) via MCP. Once connected, Claude can query all your synced business data through natural conversation.

## Install

```bash
pip install dinobase
```

Set up your data sources:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connecting Sources](/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/guides/syncing/) for background sync options.

## Configure Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dinobase": {
      "command": "dinobase",
      "args": ["serve"]
    }
  }
}
```

Or auto-generate the config:

```bash
dinobase mcp-config claude-desktop
```

If `dinobase` isn't on your PATH, use the full Python path:

```json
{
  "mcpServers": {
    "dinobase": {
      "command": "/path/to/python",
      "args": ["-m", "dinobase.mcp.server"]
    }
  }
}
```

## With background sync

Keep data fresh while Claude Desktop is running:

```json
{
  "mcpServers": {
    "dinobase": {
      "command": "dinobase",
      "args": ["serve", "--sync", "--sync-interval", "30m"]
    }
  }
}
```

## How it works

When Claude Desktop connects, it sees dynamic instructions computed from your actual database state — which sources are connected, what tables exist, and how many rows are loaded. Claude will:

1. Call `list_sources` to discover available data
2. Call `describe` on relevant tables to understand columns and types
3. Write and execute SQL via `query`
4. For mutations (UPDATE/INSERT), `query` returns a preview — Claude calls `confirm` to execute

## Available tools

The MCP server exposes these tools to Claude:

| Tool | Description |
|------|-------------|
| `query` | Execute SQL queries (DuckDB dialect) |
| `describe` | Get table schema, column types, and sample data |
| `list_sources` | List all connected sources with row counts and freshness |
| `refresh` | Re-sync a data source to get fresh data |
| `confirm` | Execute a pending mutation (write-back to source API) |
| `confirm_batch` | Execute multiple pending mutations |
| `cancel` | Cancel a pending mutation |

## Next steps

- [Getting Started](/getting-started/) — Full setup walkthrough
- [Connecting Sources](/guides/connecting-sources/) — Add your business data
- [Querying Data](/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/guides/syncing/) — Keep data fresh
- [Schema Annotations](/guides/annotations/) — Add context for AI agents
- [MCP Integration](/integrations/mcp/) — How the MCP server works
- [MCP Tools Reference](/reference/mcp-tools/) — Detailed tool schemas
