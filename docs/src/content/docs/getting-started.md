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

```bash
dinobase add stripe --api-key sk_live_...
dinobase add hubspot --api-key pat-na1-...
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

Column descriptions come from source APIs -- Stripe's OpenAPI spec, HubSpot's Properties API, Postgres column comments.

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

All queries use [DuckDB SQL syntax](https://duckdb.org/docs/sql/introduction). Tables are referenced as `schema.table`.

## Set up an agent

### MCP server (Claude Desktop, Cursor)

```bash
dinobase serve
```

Add to Claude Desktop config (`~/.claude/claude_desktop_config.json`):

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

Or auto-generate:

```bash
dinobase mcp-config
```

### CLI (Claude Code, Aider)

Shell agents use the CLI directly. All commands output JSON:

```bash
dinobase info          # what data is available
dinobase describe X    # column details
dinobase query "..."   # execute SQL
```

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
- [MCP Integration](/guides/mcp/) -- agent setup and tools reference
- [Sources Reference](/sources/overview/) -- full list of 100+ sources
