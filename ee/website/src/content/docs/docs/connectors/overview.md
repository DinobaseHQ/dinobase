---
title: Connectors Overview
description: All connectors supported by Dinobase -- SaaS APIs, databases, files, cloud storage, and MCP servers.
---

Dinobase connects to 101 connectors across four built-in categories (plus custom REST and MCP servers).

## Categories

### SaaS APIs

Connect to business tools via API keys. Data is synced to parquet using [dlt](https://dlthub.com/).

CRMs, billing, support, dev tools, communication, e-commerce, marketing, HR, project management, and more.

[Full list &rarr;](/docs/connectors/saas/)

### Databases

Connect via SQLAlchemy connection strings. Supports 16 databases: PostgreSQL, MySQL, Snowflake, BigQuery, and more.

[Full list &rarr;](/docs/connectors/databases/)

### Files

Point at parquet or CSV files (local or remote). No sync needed -- DuckDB reads at query time.

[Details &rarr;](/docs/connectors/files/)

### Cloud storage

Sync files incrementally from S3, GCS, Azure Blob, or SFTP.

[Details &rarr;](/docs/connectors/cloud-storage/)

### MCP servers

Connect any MCP server (stdio, SSE, or streamable HTTP). Dinobase auto-discovers read-only tools and syncs their output as SQL tables.

[Details &rarr;](/docs/connectors/mcp/)

### Custom REST

Any REST API via a local YAML config. Handles auth, pagination, and live or scheduled fetching.

[Details &rarr;](/docs/connectors/custom-rest/)

## Quick reference

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
| **Design** | Figma |
| **Video** | Mux |
| **Files** | Parquet, CSV (local or S3 -- read at query time, no sync needed) |

Run `dinobase connectors --pretty` to see the complete list with descriptions.
