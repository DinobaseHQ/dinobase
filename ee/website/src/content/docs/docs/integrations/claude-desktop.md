---
title: Claude Desktop
description: Connect Dinobase to Claude Desktop so Claude can query your business data directly.
---

Dinobase integrates with [Claude Desktop](https://claude.ai/download) via MCP. Once connected, Claude can query all your synced business data through natural conversation.

## Install

```bash
curl -fsSL https://dinobase.ai/install.sh | bash -s -- claude-desktop
```

Installs Dinobase via `uv`, runs `dinobase init`, and writes the `mcpServers` entry to your Claude Desktop config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS). Then add your connectors:

```bash
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connectors](/docs/guides/connecting-sources/) for the full list of 100+ supported connectors, and [Syncing & Scheduling](/docs/guides/syncing/) for background sync options.

To re-run the setup step: `dinobase install claude-desktop` (safe to run multiple times — merges rather than overwrites).

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

When Claude Desktop connects, it sees dynamic instructions computed from your actual database state — which connectors are configured, what tables exist, and how many rows are loaded. Claude will:

1. Call `list_connectors` to discover available data
2. Call `describe` on relevant tables to understand columns and types
3. Write and execute SQL via `query`
4. For mutations (UPDATE/INSERT), `query` returns a preview — Claude calls `confirm` to execute

## Available tools

The MCP server exposes these tools to Claude:

| Tool | Description |
|------|-------------|
| `query` | Execute SQL queries (DuckDB dialect) |
| `describe` | Get table schema, column types, and sample data |
| `list_connectors` | List all configured connectors with row counts and freshness |
| `refresh` | Re-sync a connector to get fresh data |
| `confirm` | Execute a pending mutation (write-back to upstream API) |
| `confirm_batch` | Execute multiple pending mutations |
| `cancel` | Cancel a pending mutation |

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connectors](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-connector joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [MCP Integration](/docs/integrations/mcp/) — How the MCP server works
- [MCP Tools Reference](/docs/reference/mcp-tools/) — Detailed tool schemas
