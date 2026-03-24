---
title: CLI Reference
description: Complete reference for all Dinobase CLI commands, options, and flags.
---

Run `dinobase --help` for a summary, or `dinobase <command> --help` for any command.

## `dinobase init`

Create the config directory and database.

```bash
dinobase init
```

Creates `~/.dinobase/` with `config.yaml` and `dinobase.duckdb`. Safe to run multiple times.

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

Source-specific flags (e.g., `--api-key`, `--connection-string`) are passed through.

```bash
dinobase add stripe --api-key sk_live_...
dinobase add parquet --path ./data/ --name analytics
dinobase add postgres --connection-string postgresql://... --name prod --sync-interval 30m
```

---

## `dinobase sources`

List all available source types.

```bash
dinobase sources
```

Groups sources by category: SaaS APIs, Databases, Cloud Storage, Files.

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

## `dinobase mcp-config`

Print MCP configuration JSON for Claude Desktop.

```bash
dinobase mcp-config
```

---

## Output format

All data commands (`status`, `query`, `describe`) output JSON by default, optimized for agent consumption. Add `--pretty` for human-readable tables.
