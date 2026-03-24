---
title: Sources Overview
description: All data sources supported by Dinobase -- SaaS APIs, databases, file sources, and cloud storage.
---

Dinobase connects to 30+ data sources across four categories.

## Categories

### SaaS APIs

Connect to business tools via API keys. Data is synced to parquet using [dlt](https://dlthub.com/).

Stripe, HubSpot, Salesforce, Shopify, GitHub, Jira, Slack, Zendesk, Notion, and many more.

[Full list &rarr;](/sources/saas/)

### Databases

Connect via SQLAlchemy connection strings. Supports PostgreSQL, MySQL, Snowflake, BigQuery, and 11 more.

[Full list &rarr;](/sources/databases/)

### File sources

Point at parquet or CSV files (local or remote). No sync needed -- DuckDB reads at query time.

[Details &rarr;](/sources/files/)

### Cloud storage

Sync files incrementally from S3, GCS, Azure Blob, or SFTP.

[Details &rarr;](/sources/cloud-storage/)

## Quick reference

| Source | Type | Auth | Pip extra |
|--------|------|------|-----------|
| Stripe | SaaS | API key | -- |
| HubSpot | SaaS | API key | -- |
| Salesforce | SaaS | Username/password | `simple_salesforce` |
| Shopify | SaaS | API key | -- |
| GitHub | SaaS | Token | -- |
| Jira | SaaS | Email + API token | -- |
| Slack | SaaS | Bot token | -- |
| Zendesk | SaaS | API token | -- |
| Notion | SaaS | API key | -- |
| PostgreSQL | Database | Connection string | -- |
| MySQL | Database | Connection string | -- |
| Snowflake | Database | Connection string | `snowflake-sqlalchemy` |
| BigQuery | Database | Connection string | `sqlalchemy-bigquery` |
| Parquet | File | Path | -- |
| CSV | File | Path | -- |
| S3 | Cloud | AWS credentials | -- |
| GCS | Cloud | Service account | -- |

Run `dinobase sources` to see the complete list with descriptions.
