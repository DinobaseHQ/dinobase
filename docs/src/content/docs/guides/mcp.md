---
title: MCP Integration
description: Set up Dinobase as an MCP server for Claude Desktop, Cursor, and other MCP-compatible agents.
---

Dinobase exposes an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that gives AI agents direct access to your business data through tool calls.

## Starting the server

```bash
dinobase serve
```

The server uses stdio transport and exposes six tools: `query`, `list_sources`, `describe`, `confirm`, `confirm_batch`, and `cancel`.

### With background sync

Keep data fresh while the server runs:

```bash
dinobase serve --sync --sync-interval 30m
```

## Client setup

### Claude Desktop

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
dinobase mcp-config
```

### Cursor

Add to your Cursor MCP configuration with the same format as Claude Desktop.

### Any MCP client

Any client that supports the MCP stdio transport can connect:

```json
{
  "command": "dinobase",
  "args": ["serve"]
}
```

If `dinobase` isn't on your PATH, use the full Python path:

```json
{
  "command": "/path/to/python",
  "args": ["-m", "dinobase.mcp.server"]
}
```

## How agents use the tools

When the MCP server starts, it provides dynamic instructions based on what data is loaded. The agent sees something like:

```
You have access to a Dinobase database -- business data synced from
multiple sources into a single SQL database (DuckDB dialect).

Connected sources:
  stripe: customers, subscriptions, charges, invoices (12,450 rows total)
  hubspot: contacts, companies, deals (8,320 rows total)

How to work with this database:
1. Use list_sources to see what data is available
2. Use describe on a table to see columns, types, annotations, and sample data
3. Use query to run SQL (DuckDB dialect, reference tables as schema.table)
```

### Typical agent workflow

1. Agent calls `list_sources` to see what's available
2. Agent calls `describe` on relevant tables to understand columns and types
3. Agent writes and executes SQL via `query`
4. For mutations (UPDATE/INSERT), `query` returns a preview -- agent calls `confirm` to execute

This is the same workflow whether the agent uses MCP or CLI -- the data and query engine are identical.

## MCP tools reference

See the full [MCP Tools reference](/reference/mcp-tools/) for parameter details.

## CLI vs MCP

Both interfaces use the same query engine and data. The difference:

| | MCP | CLI |
|--|-----|-----|
| **Transport** | stdio tool calls | bash commands |
| **Best for** | Claude Desktop, Cursor | Claude Code, Aider |
| **Token efficiency** | Standard | 27% fewer tokens |
| **Output format** | JSON (always) | JSON or `--pretty` |

For shell-capable agents, the CLI is more token-efficient. For tool-calling agents, MCP is the natural fit.
