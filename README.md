<div align="center">

<img src="readme-cover.png" alt="Dinobase" width="100%" />

# Dinobase

<strong>The agent-native database.</strong>

Connect your business data. Let AI agents query across all of it.

[![PyPI - Version](https://img.shields.io/pypi/v/dinobase.svg)](https://pypi.org/project/dinobase)
[![Tests](https://img.shields.io/badge/tests-147%20passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Docs](https://dinoplace.ai) · [Getting Started](https://dinoplace.ai/getting-started/) · [Sources](https://dinoplace.ai/sources/overview/)

</div>

---

Ask an AI agent: *"Which customers that churned last quarter had declining usage AND open support tickets?"*

It can't answer. The data lives across your CRM, billing, and support tools — each behind a separate API. You can't `JOIN` across REST endpoints. You can't `GROUP BY` across two SaaS tools. With Dinobase, the agent writes one SQL query and gets the answer.

## Quick start

```bash
pip install dinobase
```

### 1. Connect your data

```bash
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase add linear --api-key lin_api_...
dinobase sync

# Or parquet files (no sync needed)
dinobase add parquet --path ./data/events/ --name analytics

# Or databases
dinobase add postgres --connection-string postgresql://...
```

### 2. Pick your agent interface

<table>
<tr>
<td valign="top" width="50%">

**MCP server** — for Claude Desktop, Cursor, any MCP client

```bash
dinobase serve
```

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

</td>
<td valign="top" width="50%">

**CLI** — for Claude Code, Aider, any agent that runs shell

```bash
dinobase info
dinobase describe stripe.customers --pretty
dinobase query "SELECT * FROM ..." --pretty
```

All commands output JSON by default.

</td>
</tr>
</table>

### 3. Ask your agent a cross-source question

> "Which companies have closed-won deals over $100K but their subscription is past due?"

The agent writes the SQL, Dinobase executes it across your sources, and the answer comes back in seconds.

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

Each source becomes a schema. Cross-source joins work via shared columns like email. Data stays in parquet — DuckDB is the query engine and metadata store.

| Source type | How it works | Data location |
|------------|-------------|---------------|
| API sources | dlt syncs to parquet | `~/.dinobase/data/` |
| File sources | DuckDB reads directly via views | Your storage — nothing copied |

## Documentation

- **[Getting Started](https://dinoplace.ai/getting-started/)** — Install, connect, query in 5 minutes
- **[Connecting Sources](https://dinoplace.ai/guides/connecting-sources/)** — Credentials, naming, sync intervals
- **[Querying Data](https://dinoplace.ai/guides/querying/)** — Cross-source joins, aggregations, DuckDB SQL
- **[Mutations](https://dinoplace.ai/guides/mutations/)** — Write data back to sources with preview/confirm flow
- **[MCP Integration](https://dinoplace.ai/guides/mcp/)** — Agent setup for Claude Desktop, Cursor
- **[Syncing & Scheduling](https://dinoplace.ai/guides/syncing/)** — Daemon mode, per-source intervals, concurrent sync
- **[Schema Annotations](https://dinoplace.ai/guides/annotations/)** — How agents understand the data
- **[CLI Reference](https://dinoplace.ai/reference/cli/)** — All commands and flags
- **[MCP Tools Reference](https://dinoplace.ai/reference/mcp-tools/)** — All 6 agent tools
- **[Architecture](https://dinoplace.ai/project/architecture/)** — DuckDB, dlt, MCP, module structure

## Development

```bash
git clone https://github.com/DinobaseHQ/dinobase
cd dinobase
pip install -e ".[dev]"
pytest
```

## License

MIT
