<div align="center">

<img src="readme-cover.png" alt="Dinobase" width="100%" />

# 🦕 Dinobase

<strong>The data platform for agents.</strong>

Dinobase syncs 100+ sources — APIs, databases, files, MCP servers — annotates your data, and makes it SQL-ready for agents.

[![PyPI - Version](https://img.shields.io/pypi/v/dinobase.svg)](https://pypi.org/project/dinobase)
[![License](https://img.shields.io/badge/license-MIT%20Expat-blue.svg)](LICENSE)
[![Slack](https://img.shields.io/badge/slack-join%20community-4A154B?logo=slack&logoColor=white)](https://join.slack.com/t/dinobasecommunity/shared_invite/zt-3vd5zvlle-Ys24UiLvbGSg9sxbGMltJA)

[Docs](https://dinobase.ai) · [Getting Started](https://dinobase.ai/docs/getting-started/) · [Connectors](https://dinobase.ai/docs/connectors/overview/) · [Slack Community](https://join.slack.com/t/dinobasecommunity/shared_invite/zt-3vd5zvlle-Ys24UiLvbGSg9sxbGMltJA)

</div>

---

⭐️ star this repo! Thank you for your support!

---

**Your agents are flying blind.** Agent stacks built on per-connector tool calls have a structural gap: agents can't `JOIN` across APIs, have no semantic context to interpret field values, and receive paginated JSON that fills context windows. Take the question *"Which customers churned last quarter with declining usage AND open support tickets?"* — it spans three connectors and agents built on tool calls can't answer it reliably. This isn't a model problem. It's an architecture problem.

Dinobase is the data platform that fills it. Plug in every source: each connector (SaaS APIs, databases, files, MCP servers) becomes a schema. Agents write one SQL query across all connectors, write data back via SQL mutations with a preview/confirm flow, and get back a single result set. In [benchmarks across 11 LLMs](benchmarks/): **91% accuracy vs 35%, 3x faster, 16-22x cheaper per correct answer.**

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

# Or any MCP server — auto-discovers read-only tools and syncs them as SQL tables
dinobase connector create posthog_mcp --transport stdio \
  --command "npx -y @posthog/mcp-server"
dinobase sync posthog_mcp
dinobase query "SELECT * FROM posthog_mcp.list_projects LIMIT 10"
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

### 3. Ask your agent a cross-connector question

> "Which companies have closed-won deals over $100K but their subscription is past due?"

The agent writes the SQL, Dinobase executes it across your connectors, and the answer comes back in seconds.

### 4. Write data back (reverse ETL)

Agents can also mutate upstream data via SQL. Every mutation goes through a preview/confirm flow — nothing executes until confirmed.

```bash
dinobase query "UPDATE stripe.customers SET name = 'Acme Inc' WHERE id = 'cus_123'"
# Returns a preview: 1 row affected, will call Stripe API

dinobase confirm <mutation_id>
# ✓ Stripe API called (1/1 succeeded)
# ✓ Data updated
```

### 5. Use MCP servers as connectors — and call their tools directly

Connect any MCP server as a connector. Dinobase auto-discovers read-only tools and syncs them as SQL tables. Query with SQL for reads, call tools directly for writes or parameterized operations:

```bash
# Connect a server
dinobase connector create posthog_mcp --transport stdio \
  --command "npx -y @posthog/mcp-server"
dinobase sync posthog_mcp

# Query synced data as SQL
dinobase query "SELECT name, active FROM posthog_mcp.list_feature_flags"

# Browse and call tools directly
dinobase mcp servers --pretty
dinobase mcp search "dashboard"
dinobase mcp call posthog_mcp.dashboard-get '{"id": 1118504}'
```

Or call tools from Python:

```python
from dinobase.mcp import call, search, servers

result = call("posthog_mcp.dashboard-get", id=1118504)
matches = search("feature flag")
```

Agents can also call MCP tools via the `exec_code` MCP tool, which executes Python code with full access to `dinobase.mcp`.

### 6. (Optional) Enable the semantic layer

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

We tested Dinobase SQL against per-connector MCP tools across 11 LLMs on 75 questions (same models, same data, same questions):

| Metric | Dinobase (SQL) | Per-Connector MCP |
|--------|---------------|---------------|
| **Accuracy** | **91%** | 35% |
| **Avg latency** | **34s** | 106s |
| **Cost per correct answer** | **$0.027** | $0.445 |

**56pp more accurate, 3x faster, 16-22x cheaper per correct answer — across every model tested.**

See [`benchmarks/`](benchmarks/) for full results, per-model breakdown, and methodology.

---

## Connectors

101 connectors across every category. Run `dinobase sources --available --pretty` to list all.

| Category | Connectors |
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
| **MCP servers** | Any MCP server (stdio, SSE, HTTP) — auto-discovers read-only tools, syncs as SQL tables |

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

Each connector becomes a schema. Cross-connector joins work via shared columns like email. Data stays in parquet — DuckDB is the query engine and metadata store.

API connectors sync to parquet in `~/.dinobase/data/` (or cloud storage). File connectors are read directly via DuckDB views — nothing is copied.

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
- **[Connectors](https://dinobase.ai/docs/guides/connecting-sources/)** — Credentials, naming, sync intervals
- **[Querying Data](https://dinobase.ai/docs/guides/querying/)** — Cross-connector joins, aggregations, DuckDB SQL
- **[Reverse ETL (Mutations)](https://dinobase.ai/docs/guides/mutations/)** — Write data back to upstream APIs
- **[MCP Integration](https://dinobase.ai/docs/guides/mcp/)** — Agent setup for Claude Desktop, Cursor
- **[Cloud Storage Backend](https://dinobase.ai/docs/guides/cloud-storage-backend/)** — Store data in S3, GCS, or Azure
- **[Schema Annotations](https://dinobase.ai/docs/guides/annotations/)** — How agents understand the data
- **[CLI Reference](https://dinobase.ai/docs/reference/cli/)** — All commands and flags
- **[Architecture](https://dinobase.ai/docs/project/architecture/)** — DuckDB, dlt, MCP, module structure

---

## Community

Questions, feedback, or want to share what you're building? Come hang out:

- **[Join our Slack](https://join.slack.com/t/dinobasecommunity/shared_invite/zt-3vd5zvlle-Ys24UiLvbGSg9sxbGMltJA)** — chat with the team and other users
- **[Report an issue](https://github.com/DinobaseHQ/dinobase/issues)** — bugs and feature requests

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
