---
title: Getting Started
description: Install Dinobase, connect your first source, and run your first cross-source query.
---

Get up and running with Dinobase in under 5 minutes.

## Install

```bash
pip install dinobase
```

Requires Python 3.10+.

## Initialize

```bash
dinobase init
```

This creates `~/.dinobase/` with a config file and DuckDB database.

:::tip[Cloud storage]
Store data in S3, GCS, or Azure instead of local disk:
```bash
dinobase init --storage s3://my-bucket/dinobase/
```
See the [Cloud Storage Backend](/guides/cloud-storage-backend/) guide for full setup.
:::

:::tip
Set `DINOBASE_DIR` to use a custom location:
```bash
export DINOBASE_DIR=/path/to/my/dinobase
```
:::

## Connect a source

### File sources (instant)

The fastest way to start -- no sync, no API keys:

```bash
dinobase add parquet --path ./data/events/ --name analytics
dinobase add csv --path ./exports/customers.csv --name customers
```

### SaaS APIs

Connect with an API key:

```bash
dinobase add stripe --api-key sk_live_...
dinobase add hubspot --api-key pat-na1-...
dinobase sync
```

Or connect via OAuth (browser-based authorization):

```bash
dinobase auth hubspot
dinobase auth salesforce
dinobase sync
```

### Databases

```bash
dinobase add postgres --connection-string postgresql://user:pass@host/db
dinobase sync
```

:::note
If you skip CLI flags, Dinobase checks environment variables then prompts interactively.
:::

### See all available sources

```bash
dinobase sources --available --pretty
```

Lists all 100+ supported sources grouped by category (SaaS APIs, databases, cloud storage, files). See [Connecting Sources](/guides/connecting-sources/) for full details and [Sources Reference](/sources/overview/) for the complete list.

## Explore your data

```bash
# What sources are connected?
dinobase status --pretty

# Inspect a table's columns and types
dinobase describe stripe.customers --pretty
```

Example `describe` output:

```
stripe.customers (180 rows)

  id          VARCHAR   -- Unique identifier for the object.
  email       VARCHAR   -- The customer's email address.
                          Can be null
  created     INTEGER   -- Time at which the object was created.
                          Unix timestamp. Use to_timestamp() to convert.
  delinquent  BOOLEAN   -- Whether the customer has an overdue invoice.
```

Column descriptions come from source APIs -- Stripe's OpenAPI spec, HubSpot's Properties API, Postgres column comments. See [Schema Annotations](/guides/annotations/) for how to add your own.

## Run a query

```bash
dinobase query "SELECT COUNT(*) FROM stripe.customers" --pretty
```

Cross-source join:

```bash
dinobase query "
  SELECT s.email, s.name, h.company, d.amount
  FROM stripe.customers s
  JOIN hubspot.contacts h ON s.email = h.email
  JOIN hubspot.deals d ON h.id = d.contact_id
  WHERE d.dealstage = 'closedwon'
  ORDER BY d.amount DESC
  LIMIT 10
" --pretty
```

All queries use [DuckDB SQL syntax](https://duckdb.org/docs/sql/introduction). Tables are referenced as `schema.table`. See [Querying Data](/guides/querying/) for more SQL patterns and join strategies.

## Set up an agent

Dinobase works with any AI agent through two interfaces. Generate configs for all supported clients:

```bash
dinobase mcp-config
```

### Claude Code

Claude Code can use the CLI directly -- no configuration needed:

```bash
dinobase info          # what data is available
dinobase describe X    # column details
dinobase query "..."   # execute SQL
```

All commands output JSON by default, which agents parse automatically. The CLI is **27% more token-efficient** than MCP.

You can also connect via MCP by adding a `.mcp.json` to your project root:

```bash
dinobase mcp-config claude-code
```

See the [Claude Code integration guide](/integrations/claude-code/) for full details.

### Claude Desktop

```bash
dinobase mcp-config claude-desktop
```

Add the output to `~/.claude/claude_desktop_config.json`. See the [Claude Desktop integration guide](/integrations/claude-desktop/).

### Cursor

```bash
dinobase mcp-config cursor
```

Add the output to `.cursor/mcp.json`. See the [Cursor integration guide](/integrations/cursor/).

### Other agents

Dinobase integrates with many AI frameworks. See the full list of [integrations](/integrations/mcp/).

## Keep data fresh

Set freshness thresholds and sync intervals per source:

```bash
dinobase add stripe --api-key ... --freshness 30m --sync-interval 15m
```

Run a background sync daemon:

```bash
dinobase sync --schedule --interval 30m
```

Or sync alongside the MCP server:

```bash
dinobase serve --sync --sync-interval 30m
```

See [Syncing & Scheduling](/guides/syncing/) for freshness thresholds, live fetch, and scheduled sync details.

## Try with sample data

Generate realistic test data without any API keys:

```bash
pip install faker
python scripts/generate_sample_data.py
dinobase init
dinobase add parquet --path sample_data/ --name demo
dinobase query "SELECT COUNT(*) FROM demo.customers" --pretty
```

## Next steps

- [Connecting Sources](/guides/connecting-sources/) -- all source types in detail
- [Querying Data](/guides/querying/) -- SQL patterns, joins, aggregations
- [Syncing & Scheduling](/guides/syncing/) -- freshness, live fetch, daemon mode
- [Schema Annotations](/guides/annotations/) -- add context for AI agents
- [Mutations](/guides/mutations/) -- write data back to source APIs
- [MCP Integration](/integrations/mcp/) -- how the MCP server works
- [Sources Reference](/sources/overview/) -- full list of 100+ sources
- [CLI Reference](/reference/cli/) -- all commands and flags
