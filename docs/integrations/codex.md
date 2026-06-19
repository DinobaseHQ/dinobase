# Codex

Dinobase integrates with [Codex](https://openai.com/codex) via CLI. Once connected, Codex's AI agent can query all your synced business data while you code.

## Install

```bash
dinobase install codex
```

Installs Dinobase via `uv`, runs `dinobase init`, and writes CLI usage instructions to `~/.codex/AGENTS.md`. Then add your connectors:

```bash
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connectors](../guides/connecting-sources.md) for the full list of 100+ supported connectors, and [Syncing & Scheduling](../guides/syncing.md) for background sync options.

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
| `dinobase info` | Database overview — connectors, tables, row counts |
| `dinobase describe <table>` | Table schema, column types, and sample data |
| `dinobase query "<sql>"` | Execute SQL queries (DuckDB dialect) |
| `dinobase refresh [connector]` | Re-sync a connector to get fresh data |
| `dinobase confirm <id>` | Execute a pending mutation |
| `dinobase cancel <id>` | Cancel a pending mutation |

## Next steps

- [Getting Started](../getting-started.md) — Full setup walkthrough
- [Connectors](../guides/connecting-sources.md) — Add your business data
- [Querying Data](../guides/querying.md) — SQL patterns and cross-connector joins
- [Syncing & Scheduling](../guides/syncing.md) — Keep data fresh
- [Schema Annotations](../guides/annotations.md) — Add context for AI agents
- [MCP Integration](mcp.md) — How the MCP server works
- [MCP Tools Reference](../reference/mcp-tools.md) — Detailed tool schemas
