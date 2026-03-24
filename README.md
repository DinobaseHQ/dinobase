<div align="center">

# Dinobase

<strong>The agent-native database.</strong>

Connect your business data. Let AI agents query across all of it.

[![PyPI - Version](https://img.shields.io/pypi/v/dinobase.svg)](https://pypi.org/project/dinobase)
[![Tests](https://img.shields.io/badge/tests-56%20passing-brightgreen)]()
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
dinobase add salesforce --api-key ...
dinobase add zendesk --api-key ...
dinobase add shopify --api-key ...
dinobase sync

# Or parquet files (no sync needed — read at query time)
dinobase add parquet --path ./data/events/ --name analytics

# Or databases
dinobase add postgres --connection-string postgresql://...

# See all available sources
dinobase sources
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

The agent gets `query`, `describe`, and `list_sources` tools with dynamic instructions about what data is available.

</td>
<td valign="top" width="50%">

**CLI** — for Claude Code, Aider, any agent that runs shell

```bash
# What data is available?
dinobase info

# Inspect a table
dinobase describe crm.contacts

# Run a query
dinobase query "SELECT * FROM ..."
```

All commands output JSON by default. Add `--pretty` for human-readable output. **27% fewer tokens than MCP** for the same workflow.

</td>
</tr>
</table>

### 3. Ask your agent a cross-source question

> "Which companies have closed-won deals over $100K but their subscription is past due?"

The agent writes the SQL, Dinobase executes it across your sources, and the answer comes back in seconds. No data engineering required.

## Connectors

100+ sources across every category. Run `dinobase sources` to list all.

| Category | Sources |
|----------|---------|
| **CRM & Sales** | Salesforce, HubSpot, Pipedrive, Attio, Close, Copper |
| **Billing & Payments** | Stripe, Paddle, Chargebee, Recurly, Lemon Squeezy |
| **Support** | Zendesk, Intercom, Freshdesk, HelpScout, Customer.io |
| **Developer Tools** | GitHub, Jira, GitLab, Bitbucket, Sentry, Linear |
| **Communication** | Slack, Discord, Twilio, SendGrid, Mailchimp, Front, Drift |
| **E-commerce** | Shopify, WooCommerce, BigCommerce, Square |
| **Marketing & Analytics** | Google Analytics, Google Ads, Facebook Ads, Mixpanel, Amplitude, PostHog, Segment |
| **HR & Recruiting** | Personio, BambooHR, Greenhouse, Lever, Gusto, Deel |
| **Project Management** | Asana, ClickUp, Monday, Basecamp, Todoist, Trello |
| **Databases** | Postgres, MySQL, Snowflake, BigQuery, Redshift, ClickHouse, and 9 more |
| **Cloud Storage** | S3, GCS, Azure Blob, SFTP |
| **Finance** | QuickBooks, Xero, Brex, Mercury |
| **Productivity** | Notion, Airtable, Google Sheets |
| **Infrastructure** | Datadog, New Relic, PagerDuty, Cloudflare, Vercel |
| **Content & CMS** | Strapi, Contentful, Sanity, WordPress |
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
dinobase init                    Create config directory and database
dinobase add <type>              Add a source (100+ connectors — run `dinobase sources` to list)
dinobase sync [source]           Sync API sources (file sources skip this)
dinobase info                    Database overview — what an agent reads first
dinobase status                  Sources, tables, row counts, last sync
dinobase describe <table>        Columns, types, annotations, sample data
dinobase query "<sql>"           Execute SQL (DuckDB dialect)
dinobase serve                   Start MCP server (stdio transport)
dinobase mcp-config              Print MCP client configuration
```

All output commands default to JSON (agent-friendly). Use `--pretty` for human-readable tables.

## Architecture

- **[DuckDB](https://duckdb.org/)** — Embedded analytical database. Reads parquet natively from disk and S3. Zero config.
- **[dlt](https://dlthub.com/)** — Data load tool powering 100+ connectors with incremental loading.
- **[MCP](https://modelcontextprotocol.io/)** — Model Context Protocol for agent tool-calling.
- **Python** — One language for connectors, query engine, and agent interface.

Data stays in parquet. DuckDB is the query engine and metadata store. Same architecture self-hosted and cloud — swap `~/.dinobase/data/` for `s3://managed-bucket/`.

## Development

```bash
git clone https://github.com/yourusername/dinobase
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
