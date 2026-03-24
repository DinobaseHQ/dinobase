<div align="center">

<img src="readme-cover.png" alt="Dinobase" width="100%" />

# Dinobase

<strong>The agent-native database.</strong>

Connect your business data. Let AI agents query across all of it.

[![PyPI - Version](https://img.shields.io/pypi/v/dinobase.svg)](https://pypi.org/project/dinobase)
[![Tests](https://img.shields.io/badge/tests-147%20passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

Ask an AI agent: *"Which customers that churned last quarter had declining usage AND open support tickets?"*

It can't answer. The data lives across your CRM, billing, and support tools — each behind a separate API. You can't `JOIN` across REST endpoints. You can't `GROUP BY` across two SaaS tools. With Dinobase, the agent writes one SQL query and gets the answer:

```sql
SELECT c.name, c.email, d.amount, d.dealstage, t.status
FROM crm.contacts c
JOIN billing.customers b ON c.email = b.email
JOIN support.tickets t ON c.email = t.requester_email
WHERE d.dealstage = 'closedwon'
ORDER BY d.amount DESC
```

## Why Dinobase

Every AI agent that needs business data hits the same wall: data is scattered across SaaS tools that don't talk to each other. Today, you either build custom pipelines (days of work) or limit your agent to one source at a time.

Dinobase gives agents a single SQL database with all your sources connected. It handles sync, schema discovery, and cross-source joins — the agent just writes SQL.

<table>
<tr>
<td align="center" valign="top" width="33%">
<strong>Connect in minutes</strong>
<br /><br />
100+ connectors — CRMs, billing, support, analytics, databases, and more. Add any source with one command.
</td>
<td align="center" valign="top" width="33%">
<strong>Cross-source queries</strong>
<br /><br />
JOIN customers with deals with support tickets with product analytics. Questions that required a data team now have instant answers.
</td>
<td align="center" valign="top" width="33%">
<strong>Two agent interfaces</strong>
<br /><br />
MCP server for tool-calling agents (Claude Desktop, Cursor). CLI for shell-capable agents (Claude Code, Aider). Same engine, same data.
</td>
</tr>
</table>

## Quick start

```bash
pip install dinobase
```

### 1. Connect your data

```bash
# Any of 100+ SaaS sources
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase add linear --api-key lin_api_...
dinobase sync

# Or parquet files (no sync needed — read at query time)
dinobase add parquet --path ./data/events/ --name analytics

# Or databases
dinobase add postgres --connection-string postgresql://...

# See all available sources
dinobase sources --pretty
```

### 2. Pick your agent interface

<table>
<tr>
<td valign="top" width="50%">

**MCP server** — for Claude Desktop, Cursor, any MCP client

```bash
dinobase serve
```

Add to your client config:

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

Or generate it automatically:

```bash
dinobase mcp-config
```

The agent gets `query`, `describe`, `list_sources`, `confirm`, `confirm_batch`, and `cancel` tools with dynamic instructions about what data is available.

</td>
<td valign="top" width="50%">

**CLI** — for Claude Code, Aider, any agent that runs shell

```bash
# What data is available?
dinobase info

# Inspect a table
dinobase describe stripe.customers --pretty

# Run a query
dinobase query "SELECT * FROM ..." --pretty
```

All commands output JSON by default. Add `--pretty` for human-readable output. **27% fewer tokens than MCP** for the same workflow.

</td>
</tr>
</table>

### 3. Ask your agent a cross-source question

> "Which companies have closed-won deals over $100K but their subscription is past due?"

The agent writes the SQL, Dinobase executes it across your sources, and the answer comes back in seconds. No data engineering required.

## Connectors

101 sources across every category. Run `dinobase sources --pretty` to list all.

| Category | Sources |
|----------|---------|
| **CRM & Sales** | Salesforce, HubSpot, Pipedrive, Attio, Close, Copper |
| **Billing & Payments** | Stripe, Paddle, Chargebee, Recurly, Lemon Squeezy |
| **Support & Success** | Zendesk, Intercom, Freshdesk, HelpScout, Customer.io, Vitally, Gainsight |
| **Developer Tools** | GitHub, GitLab, Jira, Bitbucket, Sentry, Linear |
| **Communication** | Slack, Discord, Twilio, SendGrid, Mailchimp, Front |
| **E-commerce** | Shopify, WooCommerce, BigCommerce, Square |
| **Marketing & Analytics** | Google Analytics, Google Ads, Facebook Ads, HubSpot Marketing, Mixpanel, PostHog, Segment, Plausible, Matomo, Bing Webmaster |
| **HR & Recruiting** | Personio, BambooHR, Greenhouse, Lever, Workable, Gusto, Deel |
| **Project Management** | Asana, ClickUp, Monday, Trello, Todoist |
| **Databases** | Postgres, MySQL, MariaDB, SQL Server, Oracle, SQLite, Snowflake, BigQuery, Redshift, ClickHouse, CockroachDB, Databricks, Trino, Presto, DuckDB, MongoDB |
| **Streaming** | Kafka, Kinesis |
| **Cloud Storage** | S3, GCS, Azure Blob, SFTP |
| **Finance** | QuickBooks, Xero, Brex, Mercury |
| **Productivity** | Notion, Airtable, Google Sheets |
| **Infrastructure** | Datadog, New Relic, PagerDuty, OpsGenie, Statuspage, Cloudflare, Vercel, Netlify |
| **Content & CMS** | Strapi, Contentful, Sanity, WordPress |
| **Design** | Figma |
| **Video** | Mux |
| **Files** | Parquet, CSV (local or S3 — read at query time, no sync needed) |

## How it works

```
                    Agent (Claude, GPT, etc.)
                              |
                    +---------+---------+
                    |                   |
               MCP Server             CLI
               (tool calls)       (bash commands)
                    |                   |
                    +---------+---------+
                              |
                        Query Engine
                        (DuckDB SQL)
                              |
                 +------------+------------+
                 |            |            |
            crm.*      billing.*    analytics.*
           (synced)     (synced)    (parquet views)
```

**Two data modes, same query interface:**

| Source type | How it works | Data location |
|------------|-------------|---------------|
| API sources (100+ SaaS connectors, databases) | dlt syncs to parquet | `~/.dinobase/data/` or managed S3 |
| File sources (parquet, CSV, S3) | DuckDB reads directly via views | Your storage — nothing copied |

Each source becomes a schema (`salesforce.*`, `zendesk.*`). Cross-source joins work via shared columns like email. The `.duckdb` file stores only metadata and view definitions — data lives in parquet.

## Mutations

Dinobase supports writing data back to source systems through SQL. Mutations use a preview/confirm flow to prevent accidental changes.

```
Agent writes SQL    →  Engine previews changes  →  Agent confirms  →  API + local update
UPDATE stripe...       "2 rows affected,           confirm(id)        Stripe API called,
                        name: old → new"                              local cache updated
```

**Supported operations:** `UPDATE` and `INSERT` (no `DELETE`, `DROP`, or `TRUNCATE`).

```bash
# Via CLI
dinobase query "UPDATE stripe.customers SET name = 'Acme Inc' WHERE id = 'cus_123'"
# Returns a preview with mutation_id
dinobase confirm mut_abc123def456

# Via MCP — same flow through query and confirm tools
```

Guardrails:
- **Preview by default** — shows a per-row diff before executing
- **Row limit** — blocks mutations affecting more than 50 rows (configurable)
- **Audit log** — every mutation is recorded with per-row API results
- **Write-back** — confirmed mutations call the source API (e.g., Stripe, Linear) AND update local data for read-after-write consistency
- **Multi-statement** — `UPDATE source1...; INSERT INTO source2...` in a single call, confirmed as a batch

## Background sync

Keep data fresh with the built-in sync scheduler. Sources sync concurrently via a thread pool.

```bash
# One-time sync
dinobase sync                          # all sources
dinobase sync stripe                   # one source

# Daemon mode — sync continuously
dinobase sync --schedule               # default: every 1h
dinobase sync --schedule --interval 30m
dinobase sync --schedule --max-workers 20

# MCP server with built-in sync
dinobase serve --sync                  # serve + sync every 1h
dinobase serve --sync --sync-interval 30m
```

Per-source intervals can be set when adding a source:

```bash
dinobase add stripe --api-key sk_... --sync-interval 30m
dinobase add hubspot --api-key pat-... --sync-interval 6h
```

## Schema annotations

Agents need to understand the data, not just query it. Dinobase extracts column metadata from source APIs at sync time — not hardcoded, always current:

| Method | What gets extracted | Sources |
|--------|-------------------|---------|
| **OpenAPI spec** | Field descriptions, types, enums, formats | Stripe, and any source with a published spec |
| **Properties API** | Field descriptions, enum options, custom properties | HubSpot, Salesforce, and other CRMs |
| **Database catalog** | Column comments, foreign key constraints | Postgres, MySQL, and other SQL databases |
| **Schema introspection** | Column types, join key inference | Parquet, CSV, and all other sources |

When an agent calls `describe`, it sees what the data means:

```
$ dinobase describe salesforce.opportunities --pretty

salesforce.opportunities (342 rows)

  id          VARCHAR   — Unique identifier for the opportunity.
  name        VARCHAR   — Name of the opportunity.
  amount      DOUBLE    — Estimated total sale amount.
  stage_name  VARCHAR   — Current stage of the opportunity.
                          Values: Prospecting, Qualification, Closed Won, ...
  close_date  DATE      — Date when the opportunity is expected to close.
```

Annotations come from the source's own API — when a field changes upstream, the next sync picks it up automatically.

## CLI reference

```
dinobase init                                Create config directory and database
dinobase add <source> [flags]                Add a source (run `dinobase sources --pretty` to list all)
dinobase sync [source]                       Sync API sources (file sources skip this)
  --schedule                                   Run as a daemon, syncing on configured intervals
  --interval <duration>                        Default sync interval (e.g. 30m, 1h, 6h)
  --max-workers <n>                            Max concurrent syncs (default 10)
dinobase sources [--pretty]                  List all available source types
dinobase info                                Database overview — what an agent reads first
dinobase status [--pretty]                   Sources, tables, row counts, last sync
dinobase describe <table> [--pretty]         Columns, types, annotations, sample data
dinobase query "<sql>" [--pretty]            Execute SQL (DuckDB dialect)
  --max-rows <n>                               Maximum rows to return (default 200)
dinobase confirm <mutation_id>               Confirm and execute a pending mutation
dinobase cancel <mutation_id>                Cancel a pending mutation
dinobase serve                               Start MCP server (stdio transport)
  --sync                                       Enable background sync scheduler
  --sync-interval <duration>                   Default sync interval (default 1h)
dinobase mcp-config                          Print MCP client configuration
```

All output commands default to JSON (agent-friendly). Use `--pretty` for human-readable tables.

## MCP tools

When running as an MCP server (`dinobase serve`), agents get these tools:

| Tool | Description |
|------|-------------|
| `query(sql)` | Execute SQL (DuckDB dialect). Mutations return a preview instead of executing. |
| `list_sources()` | List all connected sources with tables, row counts, and last sync time. |
| `describe(table)` | Describe a table's columns, types, annotations, and sample rows. |
| `confirm(mutation_id)` | Confirm and execute a pending mutation (UPDATE/INSERT). |
| `confirm_batch(mutation_ids)` | Confirm multiple mutations from a multi-statement SQL. |
| `cancel(mutation_id)` | Cancel a pending mutation without executing. |

The server generates dynamic instructions from the current database state — agents see what sources are connected and how to query them, without hardcoded prompts.

## Architecture

- **[DuckDB](https://duckdb.org/)** — Embedded analytical database. Reads parquet natively from disk and S3. Zero config.
- **[dlt](https://dlthub.com/)** — Data load tool powering 100+ connectors with incremental loading.
- **[MCP](https://modelcontextprotocol.io/)** — Model Context Protocol for agent tool-calling.
- **Python** — One language for connectors, query engine, and agent interface.

Data stays in parquet. DuckDB is the query engine and metadata store. Same architecture self-hosted and cloud — swap `~/.dinobase/data/` for `s3://managed-bucket/`.

## Adding connectors

Source connectors are defined as YAML files — no Python code needed. Each YAML file specifies the API base URL, authentication, pagination, and resources to sync.

```yaml
# src/dinobase/sync/sources/apis/example.yaml
name: example
description: "Example SaaS API"
type: rest
credentials:
  - name: api_key
    flag: --api-key
    env: EXAMPLE_API_KEY
    prompt: "Example API key"
client:
  base_url: https://api.example.com/v1
  auth:
    type: bearer_token
    token: "{api_key}"
  paginator:
    type: json_link
    next_url_path: "response.next"
resources:
  - name: users
    endpoint:
      path: users
      data_selector: data
```

GraphQL sources are also supported with Relay-style cursor pagination.

## Development

```bash
git clone https://github.com/DinobaseHQ/dinobase
cd dinobase
pip install -e ".[dev]"
pytest
```

### Sample data

Generate realistic test data across multiple sources:

```bash
python scripts/generate_sample_data.py
```

Creates 7 parquet files in `sample_data/` — 200 people across 20 companies, with 89% email overlap across sources for cross-source join testing. Load it:

```bash
dinobase init
dinobase add parquet --path sample_data/ --name demo
dinobase query "SELECT COUNT(*) FROM demo.customers" --pretty
```

## Contributing

We welcome contributions. Clone the repo, install dev dependencies, and run `pytest` to verify everything works before submitting a PR.

## License

MIT
