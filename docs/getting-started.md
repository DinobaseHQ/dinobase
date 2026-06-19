# Getting Started

Get up and running with Dinobase in under 5 minutes.

## Install

**uv**

```bash
uv tool install dinobase
```

**pip**

```bash
pip install dinobase
```

**pipx**

```bash
pipx install dinobase
```

Requires Python 3.10+.

## Initialize

```bash
dinobase init
```

This creates `~/.dinobase/` with a config file and DuckDB database.

> **Tip (Cloud storage):** Store data in S3, GCS, or Azure instead of local disk:
>
> ```bash
> dinobase init --storage s3://my-bucket/dinobase/
> ```
>
> See the [Cloud Storage Backend](guides/cloud-storage-backend.md) guide for full setup.

> **Tip:** Set `DINOBASE_DIR` to use a custom location:
>
> ```bash
> export DINOBASE_DIR=/path/to/my/dinobase
> ```

## Add a connector

### File connectors (instant)

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

### Databases

```bash
dinobase add postgres --connection-string postgresql://user:pass@host/db
dinobase sync
```

> **Note:** If you skip CLI flags, Dinobase checks environment variables then prompts interactively.

### MCP servers

Connect any MCP server as a connector. Dinobase discovers the server's read-only tools and syncs their output as SQL tables:

```bash
# stdio (local process)
dinobase connector create posthog_mcp \
  --transport stdio \
  --command "npx -y @posthog/mcp-server"
dinobase sync posthog_mcp

# SSE or streamable HTTP
dinobase connector create my_server \
  --transport sse \
  --url "https://server/sse"
```

After syncing, query the data like any other connector:

```bash
dinobase query "SELECT * FROM posthog_mcp.list_projects LIMIT 10"
```

To call tools directly (for writes or tools with required arguments):

```bash
dinobase mcp call posthog_mcp.dashboard-get '{"id": 1118504}'
```

See [MCP Server Connectors](connectors/mcp.md) for full details.

### See all available connectors

```bash
dinobase connectors --available --pretty
```

Lists all 100+ supported connectors grouped by category (SaaS APIs, databases, cloud storage, files). See [Connectors](guides/connecting-sources.md) for full details and [Connectors Reference](connectors/overview.md) for the complete list.

## Explore your data

```bash
# What connectors are configured?
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

Column descriptions come from upstream APIs -- Stripe's OpenAPI spec, HubSpot's Properties API, Postgres column comments. See [Schema Annotations](guides/annotations.md) for how to add your own.

## Run a query

```bash
dinobase query "SELECT COUNT(*) FROM stripe.customers" --pretty
```

Cross-connector join:

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

All queries use [DuckDB SQL syntax](https://duckdb.org/docs/sql/introduction). Tables are referenced as `schema.table`. See [Querying Data](guides/querying.md) for more SQL patterns and join strategies.

## Set up an agent

Dinobase works with any AI agent. One command installs the MCP config for your client:

### Claude Code

```bash
dinobase install claude-code
```

Or use the CLI directly — no configuration needed:

```bash
dinobase info          # what data is available
dinobase describe X    # column details
dinobase query "..."   # execute SQL
```

See the [Claude Code integration guide](integrations/claude-code.md) for full details.

### Claude Desktop

```bash
dinobase install claude-desktop
```

Writes the config to your Claude Desktop config file automatically. See the [Claude Desktop integration guide](integrations/claude-desktop.md).

### Cursor

```bash
dinobase install cursor
```

Writes `.cursor/mcp.json` in your project root. See the [Cursor integration guide](integrations/cursor.md).

### OpenClaw

```bash
openclaw skills install dinobase
```

See the [OpenClaw integration guide](integrations/openclaw.md).

### Other agents

Dinobase integrates with many AI frameworks. See the full list of [integrations](integrations/mcp.md).

## Keep data fresh

Set freshness thresholds and sync intervals per connector:

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

See [Syncing & Scheduling](guides/syncing.md) for freshness thresholds, live fetch, and scheduled sync details.

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

- [Connectors](guides/connecting-sources.md) -- all connector types in detail
- [Querying Data](guides/querying.md) -- SQL patterns, joins, aggregations
- [Syncing & Scheduling](guides/syncing.md) -- freshness, live fetch, daemon mode
- [Schema Annotations](guides/annotations.md) -- add context for AI agents
- [Mutations](guides/mutations.md) -- write data back to upstream APIs
- [MCP Integration](integrations/mcp.md) -- how the MCP server works
- [Connectors Reference](connectors/overview.md) -- full list of 100+ connectors
- [CLI Reference](reference/cli.md) -- all commands and flags
