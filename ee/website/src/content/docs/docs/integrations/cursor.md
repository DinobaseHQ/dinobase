---
title: Cursor
description: Connect Dinobase to Cursor so its AI agent can query your business data directly.
---

Dinobase integrates with [Cursor](https://cursor.com) via MCP. Once connected, Cursor's AI agent can query all your synced business data while you code.

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

See [Connecting Sources](/docs/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/docs/guides/syncing/) for background sync options.

## Configure Cursor

Run the install command from your project root:

```bash
dinobase install cursor
```

This writes CLI usage instructions to `AGENTS.md` in your current directory, wrapped in `<dinobase>` tags. Safe to run multiple times — it replaces the existing block if present.

Cursor's agent can then run shell commands like `dinobase info`, `dinobase describe stripe.customers`, and `dinobase query "SELECT ..."` to answer questions about your data.

## How it works

The agent will:

1. Run `dinobase info` to discover available data
2. Run `dinobase describe <table>` to understand columns and types
3. Run `dinobase query "<sql>"` to execute SQL (DuckDB dialect)
4. For mutations (UPDATE/INSERT), `query` returns a preview — the agent runs `dinobase confirm <id>` to execute

## Alternative: MCP server

If you prefer MCP, run `dinobase mcp-config cursor` to get the JSON config, then add it to `.cursor/mcp.json` in your project root.

## Available CLI commands

| Command | Description |
|---------|-------------|
| `dinobase info` | Database overview — sources, tables, row counts |
| `dinobase describe <table>` | Table schema, column types, and sample data |
| `dinobase query "<sql>"` | Execute SQL queries (DuckDB dialect) |
| `dinobase refresh [source]` | Re-sync a data source to get fresh data |
| `dinobase confirm <id>` | Execute a pending mutation |
| `dinobase cancel <id>` | Cancel a pending mutation |

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connecting Sources](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [MCP Integration](/docs/integrations/mcp/) — How the MCP server works
- [MCP Tools Reference](/docs/reference/mcp-tools/) — Detailed tool schemas
