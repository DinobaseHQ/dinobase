---
title: Codex
description: Connect Dinobase to Codex so its AI agent can query your business data directly.
---

Dinobase integrates with [Codex](https://openai.com/codex) via CLI. Once connected, Codex's AI agent can query all your synced business data while you code.

## Install

```bash
curl -fsSL https://dinobase.ai/install.sh | bash -s -- codex
```

Installs Dinobase via `uv`, runs `dinobase init`, and writes CLI usage instructions to `~/.codex/AGENTS.md`. Then connect your data sources:

```bash
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connecting Sources](/docs/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/docs/guides/syncing/) for background sync options.

Codex can run shell commands directly, so no MCP configuration is needed. Just ask questions about your data and Codex will run `dinobase info`, `dinobase describe stripe.customers`, and `dinobase query "SELECT ..."` to answer them.

To re-run the setup step: `dinobase install codex` (safe to run multiple times — replaces the existing block).

## How it works

The agent will:

1. Run `dinobase info` to discover available data
2. Run `dinobase describe <table>` to understand columns and types
3. Run `dinobase query "<sql>"` to execute SQL (DuckDB dialect)
4. For mutations (UPDATE/INSERT), `query` returns a preview — the agent runs `dinobase confirm <id>` to execute

## Alternative: MCP server

If you prefer MCP, run `dinobase mcp-config codex` to get the JSON config, then add it to your Codex MCP configuration.

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
