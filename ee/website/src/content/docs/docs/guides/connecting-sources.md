---
title: Connecting Sources
description: How to add SaaS APIs, databases, and file sources to Dinobase.
---

Dinobase supports three categories of data sources.

| Category | Examples | Sync needed? | Storage |
|----------|----------|-------------|---------|
| **SaaS APIs** | Stripe, HubSpot, GitHub | Yes | dlt syncs to parquet |
| **Databases** | PostgreSQL, MySQL, Snowflake | Yes | dlt syncs to parquet |
| **File sources** | Parquet, CSV, S3, GCS | No | DuckDB reads files directly |

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

By default, the source name matches the type. Use `--name` for multiple instances:

```bash
dinobase add stripe --api-key sk_live_... --name stripe_prod
dinobase add stripe --api-key sk_test_... --name stripe_test
```

Creates separate schemas: `stripe_prod.*` and `stripe_test.*`.

### Sync intervals

Set per-source intervals (used with `dinobase sync --schedule`):

```bash
dinobase add stripe --api-key sk_live_... --sync-interval 30m
dinobase add hubspot --api-key pat-... --sync-interval 1h
```

Supported formats: `30s`, `5m`, `1h`, `6h`, `1d`.

## SaaS API sources

Powered by [dlt](https://dlthub.com/) verified sources and REST API connectors.

```bash
dinobase add stripe --api-key sk_live_...
dinobase add hubspot --api-key pat-na1-...
dinobase sync
```

After syncing, data is stored as parquet and queryable as `stripe.*`, `hubspot.*`, etc.

See [SaaS APIs reference](/docs/sources/saas/) for all supported services.

## Database sources

Connect via connection string (SQLAlchemy-compatible):

```bash
dinobase add postgres --connection-string postgresql://user:pass@host:5432/db
dinobase add mysql --connection-string mysql://user:pass@host:3306/db
dinobase add snowflake --connection-string snowflake://user:pass@account/db/schema
dinobase add sqlite --path /path/to/database.db
```

See [Databases reference](/docs/sources/databases/) for all supported databases.

## File sources

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

See [File Sources reference](/docs/sources/files/) for more details.

## Viewing configured sources

```bash
# List all available source types
dinobase sources

# See what's actually connected and loaded
dinobase status --pretty
```

## Removing a source

Edit `~/.dinobase/config.yaml` directly to remove a source entry. Data stays in DuckDB until overwritten.
