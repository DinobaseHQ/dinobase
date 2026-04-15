---
title: Connectors
description: How to add SaaS APIs, databases, files, MCP servers, and custom REST connectors to Dinobase.
---

A **connector** is anything Dinobase can read from (and often write back to): a SaaS API, a database, a file path, an MCP server, or a custom REST endpoint. Each connector becomes a schema in DuckDB.

| Category | Examples | Sync needed? | Storage |
|----------|----------|-------------|---------|
| **SaaS APIs** | Stripe, HubSpot, GitHub | Yes | dlt syncs to parquet |
| **Databases** | PostgreSQL, MySQL, Snowflake | Yes | dlt syncs to parquet |
| **Files** | Parquet, CSV, S3, GCS | No | DuckDB reads files directly |
| **MCP servers** | Any stdio/SSE/HTTP MCP server | Yes | Tool output cached as JSON views |
| **Custom REST** | Any REST API via local YAML config | Yes/live | dlt fetches, cached as JSON views |

## The `add` command

```bash
dinobase add <type> [credentials] [options]
```

### Credential resolution order

1. **CLI flags** -- `--api-key sk_live_...`
2. **Environment variables** -- `STRIPE_SECRET_KEY`
3. **Interactive prompt** -- asks if neither is set

```bash
# These are equivalent:
dinobase add stripe --api-key sk_live_...

export STRIPE_SECRET_KEY=sk_live_...
dinobase add stripe
```

### Custom naming

By default, the connector name matches the type. Use `--name` for multiple instances:

```bash
dinobase add stripe --api-key sk_live_... --name stripe_prod
dinobase add stripe --api-key sk_test_... --name stripe_test
```

Creates separate schemas: `stripe_prod.*` and `stripe_test.*`.

### Sync intervals

Set per-connector intervals (used with `dinobase sync --schedule`):

```bash
dinobase add stripe --api-key sk_live_... --sync-interval 30m
dinobase add hubspot --api-key pat-... --sync-interval 1h
```

Supported formats: `30s`, `5m`, `1h`, `6h`, `1d`.

## SaaS API connectors

Powered by [dlt](https://dlthub.com/) verified sources and REST API connectors.

```bash
dinobase add stripe --api-key sk_live_...
dinobase add hubspot --api-key pat-na1-...
dinobase sync
```

After syncing, data is stored as parquet and queryable as `stripe.*`, `hubspot.*`, etc.

See [SaaS APIs reference](/docs/connectors/saas/) for all supported services.

## Database connectors

Connect via connection string (SQLAlchemy-compatible):

```bash
dinobase add postgres --connection-string postgresql://user:pass@host:5432/db
dinobase add mysql --connection-string mysql://user:pass@host:3306/db
dinobase add snowflake --connection-string snowflake://user:pass@account/db/schema
dinobase add sqlite --path /path/to/database.db
```

See [Databases reference](/docs/connectors/databases/) for all supported databases.

## File connectors

No sync needed. DuckDB reads files at query time through views.

```bash
# Local directory of parquet files
dinobase add parquet --path ./data/events/ --name analytics

# Single CSV file
dinobase add csv --path ./exports/report.csv --name report

# S3
dinobase add parquet --path s3://bucket/prefix/ --name warehouse

# GCS
dinobase add parquet --path gs://bucket/data/ --name warehouse
```

### Path resolution

| Input | Behavior |
|-------|----------|
| Directory (`./data/`) | Finds all matching files recursively |
| Single file (`./data/events.parquet`) | One table from the file |
| Glob (`./data/*.parquet`) | Matches by pattern |
| S3 URL (`s3://bucket/prefix/`) | DuckDB reads from S3 at query time |
| GCS URL (`gs://bucket/prefix/`) | DuckDB reads from GCS at query time |

Each file becomes a table named after its filename: `events.parquet` becomes the `events` table.

See [Files reference](/docs/connectors/files/) for more details.

## Custom REST connectors

Connect any REST API endpoint by writing a local YAML config. Data is fetched via dlt (handles auth, pagination) and cached as JSON files that DuckDB queries via `read_json_auto()`.

```bash
dinobase connector create posthog_flags \
  --url "https://app.posthog.com/api/" \
  --endpoint "projects/123/feature_flags/" \
  --data-selector results
dinobase add posthog_flags --api-key phx_xxx
dinobase query "SELECT name, active FROM posthog_flags.feature_flags"
```

See the full [Custom REST Connectors reference](/docs/connectors/custom-rest/) for the YAML format, auth types, fetch modes, and connector management commands.

## MCP server connectors

Connect any MCP server (stdio, SSE, or streamable HTTP) as a connector. Dinobase auto-discovers read-only tools and syncs their output as SQL tables. For writes or parameterized calls, use `dinobase mcp call` or the Python API.

```bash
dinobase connector create posthog_mcp \
  --transport stdio \
  --command "npx -y @posthog/mcp-server"
dinobase sync posthog_mcp
dinobase query "SELECT * FROM posthog_mcp.list_projects LIMIT 10"
```

See the full [MCP Server Connectors reference](/docs/connectors/mcp/) for the YAML format, tool-selection rules, and direct tool-call examples (CLI + Python).

---

## Viewing configured connectors

```bash
# List all available connector types
dinobase connectors

# See what's actually connected and loaded
dinobase status --pretty
```

## Removing a connector

Edit `~/.dinobase/config.yaml` directly to remove a connector entry. Data stays in DuckDB until overwritten.
