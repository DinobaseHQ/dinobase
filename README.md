<div align="center">

<img src="readme-cover.png" alt="Dinobase" width="100%" />

# 🦕 Dinobase

<strong>The agent-first database.</strong>

Connect your business data. Let AI agents query across all of it.

[![PyPI - Version](https://img.shields.io/pypi/v/dinobase.svg)](https://pypi.org/project/dinobase)
[![License](https://img.shields.io/badge/license-MIT%20Expat-blue.svg)](LICENSE)

[Docs](https://dinobase.ai) · [Getting Started](https://dinobase.ai/docs/getting-started/) · [Sources](https://dinobase.ai/docs/sources/overview/)

</div>

---

⭐️ star this repo! Thank you for your support!

---

Agent stacks built on per-source tool calls have a structural gap: agents can't `JOIN` across APIs, have no semantic context to interpret field values, and receive paginated JSON that fills context windows. Take the question *"Which customers churned last quarter with declining usage AND open support tickets?"* — it spans three sources and agents built on tool calls can't answer it reliably. This isn't a model problem. It's an architecture problem.

Dinobase is the query layer that fills it. Each source (SaaS APIs, databases, file storages) becomes a schema. Agents write one SQL query across all sources, write data back via SQL mutations with a preview/confirm flow, and get back a single result set. In [benchmarks across 11 LLMs](benchmarks/): **91% accuracy vs 35%, 3x faster, 16-22x cheaper per correct answer.**

---

## Quick start

```bash
# recommended — installs everything automatically
curl -fsSL https://dinobase.ai/install.sh | bash

# or with uv
uv tool install dinobase

# or with pip
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

**CLI** — for Claude Code, Cursor, Codex, Aider, any agent that runs shell

```bash
dinobase install claude-code   # Claude Code (~/.claude/CLAUDE.md)
dinobase install cursor        # Cursor (./AGENTS.md)
dinobase install codex         # Codex (~/.codex/AGENTS.md)
```

Writes usage instructions to the tool's instructions file. Agents run `dinobase info`, `dinobase describe`, and `dinobase query` directly.

</td>
<td valign="top" width="50%">

**MCP server** — for Claude Desktop, any MCP client

```bash
dinobase install claude-desktop   # Claude Desktop (writes config automatically)
dinobase serve                    # any other MCP client
```

`dinobase serve` starts the MCP server on stdio. Run `dinobase mcp-config <client>` to get the JSON snippet to paste into your client's config.

</td>
</tr>
</table>

### 3. Ask your agent a cross-source question

> "Which companies have closed-won deals over $100K but their subscription is past due?"

The agent writes the SQL, Dinobase executes it across your sources, and the answer comes back in seconds.

### 4. Write data back (reverse ETL)

Agents can also mutate source data via SQL. Every mutation goes through a preview/confirm flow — nothing executes until confirmed.

```bash
dinobase query "UPDATE stripe.customers SET name = 'Acme Inc' WHERE id = 'cus_123'"
# Returns a preview: 1 row affected, will call Stripe API

dinobase confirm <mutation_id>
# ✓ Stripe API called (1/1 succeeded)
# ✓ Data updated
```

### 5. (Optional) Enable the semantic layer

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

After every sync, Dinobase automatically runs a Claude agent in the background to annotate your data — table descriptions, column docs, PII flags, and relationship graphs. Agents can then `describe` any table and get full semantic context.

```bash
dinobase describe stripe.subscriptions --pretty
# stripe.subscriptions (1,420 rows)
# Description: Active and historical customer subscriptions
#
#   customer_id  VARCHAR  -- References customers.id
#   status       VARCHAR  -- Values: active, past_due, canceled, trialing
#   ...
# Related tables:
#   stripe.customers  (customer_id → id, many_to_one)
```

Set `DINOBASE_AUTO_ANNOTATE=false` to disable. See [Semantic Layer docs](https://dinobase.ai/docs/guides/annotations/).

---

## Benchmark

We tested Dinobase SQL against per-source MCP tools across 11 LLMs on 75 questions (same models, same data, same questions):

| Metric | Dinobase (SQL) | Per-Source MCP |
|--------|---------------|---------------|
| **Accuracy** | **91%** | 35% |
| **Avg latency** | **34s** | 106s |
| **Cost per correct answer** | **$0.027** | $0.445 |

**56pp more accurate, 3x faster, 16-22x cheaper per correct answer — across every model tested.**

See [`benchmarks/`](benchmarks/) for full results, per-model breakdown, and methodology.

---

## Connectors

101 sources across every category. Run `dinobase sources --available --pretty` to list all.

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
| **Design & Video** | Figma, Mux |
| **Files** | Parquet, CSV (local or S3 — read at query time, no sync needed) |

---

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

API sources sync to parquet in `~/.dinobase/data/` (or cloud storage). File sources are read directly via DuckDB views — nothing is copied.

### Cloud storage

Store data in S3, GCS, or Azure instead of local disk:

```bash
dinobase init --storage s3://my-bucket/dinobase/
# or
export DINOBASE_STORAGE_URL=s3://my-bucket/dinobase/
```

Supports Amazon S3, Google Cloud Storage, Azure Blob Storage, and S3-compatible services (MinIO, R2). See [Cloud Storage docs](https://dinobase.ai/docs/guides/cloud-storage-backend/).

---

## Integrations

Works with every major agent framework:
[CrewAI](https://dinobase.ai/docs/integrations/crewai/) · [LangChain / LangGraph](https://dinobase.ai/docs/integrations/langchain/) · [LlamaIndex](https://dinobase.ai/docs/integrations/llamaindex/) · [Pydantic AI](https://dinobase.ai/docs/integrations/pydantic-ai/) · [Vercel AI SDK](https://dinobase.ai/docs/integrations/vercel-ai/) · [Mastra](https://dinobase.ai/docs/integrations/mastra/) · [OpenClaw](https://dinobase.ai/docs/integrations/openclaw/)

---

## Documentation

- **[Getting Started](https://dinobase.ai/docs/getting-started/)** — Install, connect, and query in 5 minutes
- **[Connecting Sources](https://dinobase.ai/docs/guides/connecting-sources/)** — Credentials, naming, sync intervals
- **[Querying Data](https://dinobase.ai/docs/guides/querying/)** — Cross-source joins, aggregations, DuckDB SQL
- **[Reverse ETL (Mutations)](https://dinobase.ai/docs/guides/mutations/)** — Write data back to source APIs
- **[MCP Integration](https://dinobase.ai/docs/guides/mcp/)** — Agent setup for Claude Desktop, Cursor
- **[Cloud Storage Backend](https://dinobase.ai/docs/guides/cloud-storage-backend/)** — Store data in S3, GCS, or Azure
- **[Schema Annotations](https://dinobase.ai/docs/guides/annotations/)** — How agents understand the data
- **[CLI Reference](https://dinobase.ai/docs/reference/cli/)** — All commands and flags
- **[Architecture](https://dinobase.ai/docs/project/architecture/)** — DuckDB, dlt, MCP, module structure

---

## Development

```bash
git clone https://github.com/DinobaseHQ/dinobase
pip install -e ".[dev]"
pytest
```

---

## License

MIT Expat
