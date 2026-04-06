---
title: Claude Code
description: Connect Dinobase to Claude Code so it can query your business data via CLI or MCP.
---

Dinobase works with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) out of the box. Claude Code can use either the CLI (more token-efficient) or the MCP server — both give access to the same data and query engine.

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

## Setup

Run the install command to add Dinobase instructions to your global `~/.claude/CLAUDE.md`:

```bash
dinobase install claude-code
```

This writes CLI usage instructions wrapped in `<dinobase>` tags. Safe to run multiple times — it replaces the existing block if present.

Claude Code can run shell commands directly, so no MCP configuration is needed. Just ask questions about your data:

> "Query my Dinobase for customers who churned last quarter"

Claude Code will run commands like `dinobase info`, `dinobase describe stripe.customers`, and `dinobase query "SELECT ..."` to answer your question.

The CLI outputs JSON by default, which Claude Code parses automatically. This is **27% more token-efficient** than MCP.

## Alternative: MCP server

If you prefer MCP, you can manually configure it. Run `dinobase mcp-config claude-code` to get the JSON config, then add it to your project's `.mcp.json`.

## Available commands

| Command | Description |
|---------|-------------|
| `dinobase info` | Database overview — sources, tables, row counts |
| `dinobase status` | Source freshness and sync history |
| `dinobase describe <table>` | Table schema, column types, and sample data |
| `dinobase query "<sql>"` | Execute SQL queries (DuckDB dialect) |
| `dinobase refresh [source]` | Re-sync a data source |
| `dinobase confirm <id>` | Execute a pending mutation |
| `dinobase cancel <id>` | Cancel a pending mutation |

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connecting Sources](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [CLI Reference](/docs/reference/cli/) — All commands and flags
