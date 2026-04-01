---
title: CLI Reference
description: Complete reference for all Dinobase CLI commands, options, and flags.
---

Run `dinobase --help` for a summary, or `dinobase <command> --help` for any command.

## `dinobase init`

Create the config directory and database.

```bash
dinobase init [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--storage` | Cloud storage URL (e.g., `s3://bucket/dinobase/`, `gs://bucket/dinobase/`, `az://container/dinobase/`) |

Creates `~/.dinobase/` with `config.yaml` and `dinobase.duckdb`. Safe to run multiple times.

With `--storage`, data is stored in cloud storage instead of locally. See the [Cloud Storage Backend](/docs/guides/cloud-storage-backend/) guide.

```bash
dinobase init                                    # local (default)
dinobase init --storage s3://bucket/dinobase/    # S3
dinobase init --storage gs://bucket/dinobase/    # GCS
dinobase init --storage az://container/dinobase/ # Azure
```

---

## `dinobase add <type>`

Add a data source.

```bash
dinobase add <source_type> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--name` | Custom name for the source (defaults to type) |
| `--path` | Path to files (parquet/csv sources only) |
| `--sync-interval` | Sync interval (e.g., `30m`, `1h`, `6h`) |
| `--freshness` | Freshness threshold (e.g., `1h`, `30m`). Defaults: 1h for SaaS, 6h for databases |

Source-specific flags (e.g., `--api-key`, `--connection-string`) are passed through.

```bash
dinobase add stripe --api-key sk_live_...
dinobase add stripe --api-key sk_live_... --freshness 30m
dinobase add parquet --path ./data/ --name analytics
dinobase add postgres --connection-string postgresql://... --name prod --sync-interval 30m
```

---

## `dinobase sources`

List connected data sources, or all available source types.

```bash
dinobase sources [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--available` | Show all available source types (not just connected) |
| `--pretty` | Human-readable output |

By default shows only your connected sources. Use `--available` to see all 100+ supported source types grouped by category.

---

## `dinobase sync [source]`

Sync data from connected sources.

```bash
dinobase sync [SOURCE_NAME] [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--schedule` | off | Run as daemon |
| `--interval` | `1h` | Default interval for `--schedule` |
| `--max-workers` | `10` | Max concurrent syncs |

```bash
dinobase sync                              # all sources, once
dinobase sync stripe                       # one source
dinobase sync --schedule --interval 30m    # daemon mode
```

---

## `dinobase refresh [source]`

Re-sync sources to get fresh data.

```bash
dinobase refresh [SOURCE_NAME] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--stale` | Refresh only sources that exceed their freshness threshold |
| `--pretty` | Human-readable output |

```bash
dinobase refresh                 # refresh all sources
dinobase refresh stripe          # refresh one source
dinobase refresh --stale         # refresh only stale sources
dinobase refresh --stale --pretty
```

Without arguments, refreshes all non-file sources. Use `--stale` to only refresh sources past their freshness threshold.

---

## `dinobase status`

Show status of all sources.

```bash
dinobase status [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--pretty` | Human-readable output |

---

## `dinobase query "<sql>"`

Execute a SQL query (DuckDB dialect).

```bash
dinobase query "<sql>" [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--pretty` | off | Table output |
| `--max-rows` | `200` | Max rows returned |

```bash
dinobase query "SELECT * FROM stripe.customers LIMIT 5" --pretty
dinobase query "SELECT COUNT(*) FROM hubspot.contacts"
```

---

## `dinobase describe <table>`

Describe a table's columns, types, annotations, and sample data.

```bash
dinobase describe <table> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--pretty` | Human-readable output |

`table` can be `schema.table` or just `table` (searches all schemas).

---

## `dinobase info`

Show database overview for agents. Outputs the same text used as MCP server instructions.

```bash
dinobase info
```

No options. Always plain text.

---

## `dinobase serve`

Start the MCP server (stdio transport).

```bash
dinobase serve [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--sync` | off | Enable background sync |
| `--sync-interval` | `1h` | Sync interval |

```bash
dinobase serve                              # MCP server only
dinobase serve --sync --sync-interval 30m   # with background sync
```

---

## `dinobase confirm <mutation_id>`

Confirm and execute a pending mutation.

```bash
dinobase confirm <mutation_id>
```

Mutations submitted via `dinobase query "UPDATE ..."` return a preview with a `mutation_id`. Use this command to execute it.

```bash
dinobase query "UPDATE stripe.customers SET name = 'Acme' WHERE id = 'cus_123'"
# Returns preview with mutation_id
dinobase confirm mut_abc123def456
```

---

## `dinobase cancel <mutation_id>`

Cancel a pending mutation without executing it.

```bash
dinobase cancel <mutation_id>
```

---

## `dinobase auth <type>`

Connect a source via OAuth (browser-based authorization).

```bash
dinobase auth <source_type> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--name` | Custom name for the source (defaults to type) |
| `--proxy-url` | OAuth proxy URL (or set `DINOBASE_OAUTH_PROXY_URL`) |

Opens your browser to authorize Dinobase to access the source. Tokens are stored locally and refreshed automatically on sync.

```bash
dinobase auth hubspot
dinobase auth salesforce --name my_salesforce
```

---

## `dinobase mcp-config [client]`

Print MCP configuration for Claude Code, Claude Desktop, or Cursor.

```bash
dinobase mcp-config [CLIENT]
```

| Argument | Description |
|----------|-------------|
| `claude-desktop` | Config for `~/.claude/claude_desktop_config.json` |
| `claude-code` | Config for `.mcp.json` (project root) |
| `cursor` | Config for `.cursor/mcp.json` (project root) |

Without arguments, prints configs for all three clients.

```bash
dinobase mcp-config                # show all configs
dinobase mcp-config claude-desktop # Claude Desktop only
dinobase mcp-config claude-code    # Claude Code only
dinobase mcp-config cursor         # Cursor only
```

---

## Output format

All data commands (`status`, `query`, `describe`) output JSON by default, optimized for agent consumption. Add `--pretty` for human-readable tables.
