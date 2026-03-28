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

See [Connecting Sources](/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/guides/syncing/) for background sync options.

## Option 1: CLI (recommended)

Claude Code can run shell commands directly, so no configuration is needed. Just ask questions about your data:

> "Query my Dinobase for customers who churned last quarter"

Claude Code will run commands like `dinobase info`, `dinobase describe stripe.customers`, and `dinobase query "SELECT ..."` to answer your question.

The CLI outputs JSON by default, which Claude Code parses automatically. This is **27% more token-efficient** than the MCP transport.

## Option 2: MCP server

Add to `.mcp.json` in your project root:

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
dinobase mcp-config claude-code
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

## CLI vs MCP

| | CLI | MCP |
|--|-----|-----|
| **Setup** | None (just install dinobase) | Add `.mcp.json` config |
| **Token efficiency** | 27% fewer tokens | Standard |
| **Output format** | JSON or `--pretty` | JSON (always) |

Both use the same query engine and data. The CLI is recommended for Claude Code since it's simpler and more efficient.

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

- [Getting Started](/getting-started/) — Full setup walkthrough
- [Connecting Sources](/guides/connecting-sources/) — Add your business data
- [Querying Data](/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/guides/syncing/) — Keep data fresh
- [CLI Reference](/reference/cli/) — All commands and flags
