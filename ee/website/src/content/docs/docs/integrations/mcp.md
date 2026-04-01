---
title: MCP
description: How Dinobase's MCP server works, and how to connect any MCP-compatible client.
---

Dinobase exposes an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that gives AI agents direct access to your business data through tool calls.

## Prerequisites

Before connecting an MCP client, set up Dinobase with your data:

```bash
pip install dinobase
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase sync
```

See [Getting Started](/docs/getting-started/) for a full walkthrough, [Connecting Sources](/docs/guides/connecting-sources/) for the 100+ supported sources, and [Cloud Storage Backend](/docs/guides/cloud-storage-backend/) for team/remote setups.

## Starting the server

```bash
dinobase serve
```

The server uses stdio transport and exposes seven tools: `query`, `list_sources`, `describe`, `confirm`, `confirm_batch`, `cancel`, and `refresh`.

### With background sync

Keep data fresh while the server runs:

```bash
dinobase serve --sync --sync-interval 30m
```

See [Syncing & Scheduling](/docs/guides/syncing/) for more sync options.

## Installing into your client

The `dinobase install` command writes the MCP config directly to the right file for your client:

```bash
dinobase install claude-code      # runs: claude mcp add dinobase -- dinobase serve
dinobase install claude-desktop   # writes to Claude Desktop config file
dinobase install cursor           # writes .cursor/mcp.json in current directory
```

Safe to run multiple times — it merges the `dinobase` entry rather than overwriting the whole file.

## Client setup guides

- [Claude Code](/docs/integrations/claude-code/) — CLI (recommended) or MCP
- [Claude Desktop](/docs/integrations/claude-desktop/) — MCP via `claude_desktop_config.json`
- [Cursor](/docs/integrations/cursor/) — MCP via `.cursor/mcp.json`

### Any MCP client

Any client that supports the MCP stdio transport can connect using the same server entry:

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

See the full [MCP Tools reference](/docs/reference/mcp-tools/) for parameter details.

## CLI vs MCP

Both interfaces use the same query engine and data. The difference:

| | MCP | CLI |
|--|-----|-----|
| **Transport** | stdio tool calls | bash commands |
| **Best for** | Claude Desktop, Cursor | Claude Code, Aider |
| **Token efficiency** | Standard | 27% fewer tokens |
| **Output format** | JSON (always) | JSON or `--pretty` |

For shell-capable agents, the CLI is more token-efficient. For tool-calling agents, MCP is the natural fit.

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connecting Sources](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [MCP Tools Reference](/docs/reference/mcp-tools/) — Detailed tool schemas
