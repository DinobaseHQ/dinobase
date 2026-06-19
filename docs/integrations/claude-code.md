# Claude Code

Dinobase works with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) out of the box. Claude Code can use either the CLI (more token-efficient) or the MCP server — both give access to the same data and query engine.

## Install

```bash
dinobase install claude-code
```

Installs Dinobase via `uv`, runs `dinobase init`, and writes CLI usage instructions to `~/.claude/CLAUDE.md`. Then add your connectors:

```bash
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connectors](../guides/connecting-sources.md) for the full list of 100+ supported connectors, and [Syncing & Scheduling](../guides/syncing.md) for background sync options.

Claude Code can run shell commands directly, so no MCP configuration is needed. Just ask questions about your data:

> "Query my Dinobase for customers who churned last quarter"

Claude Code will run commands like `dinobase info`, `dinobase describe stripe.customers`, and `dinobase query "SELECT ..."` to answer your question.

The CLI outputs JSON by default, which Claude Code parses automatically. This is **27% more token-efficient** than MCP.

To re-run the setup step: `dinobase install claude-code` (safe to run multiple times — replaces the existing block).

## Alternative: MCP server

If you prefer MCP, you can manually configure it. Run `dinobase mcp-config claude-code` to get the JSON config, then add it to your project's `.mcp.json`.

## Available commands

| Command | Description |
|---------|-------------|
| `dinobase info` | Database overview — connectors, tables, row counts |
| `dinobase status` | Connector freshness and sync history |
| `dinobase describe <table>` | Table schema, column types, and sample data |
| `dinobase query "<sql>"` | Execute SQL queries (DuckDB dialect) |
| `dinobase refresh [connector]` | Re-sync a connector |
| `dinobase confirm <id>` | Execute a pending mutation |
| `dinobase cancel <id>` | Cancel a pending mutation |

## Next steps

- [Getting Started](../getting-started.md) — Full setup walkthrough
- [Connectors](../guides/connecting-sources.md) — Add your business data
- [Querying Data](../guides/querying.md) — SQL patterns and cross-connector joins
- [Syncing & Scheduling](../guides/syncing.md) — Keep data fresh
- [CLI Reference](../reference/cli.md) — All commands and flags
