---
title: Cloud Storage Backend
description: Store Dinobase data in S3, GCS, or Azure instead of local disk. Run servers without local storage.
---

By default, Dinobase stores everything locally in `~/.dinobase/`. With cloud storage, your synced data and metadata live in S3, GCS, or Azure Blob Storage instead. This lets you:

- Run Dinobase servers without local disk (containers, cloud VMs)
- Share data across multiple machines or agents
- Deploy a centralized data layer for your team

## How it works

In cloud mode, Dinobase uses an **in-memory DuckDB** instance that reads data directly from cloud parquet files:

```
Source API --> dlt sync --> s3://bucket/dinobase/data/{source}/{table}/*.parquet
                                        |
                           DuckDB (in-memory) reads via views
                                        |
                           _live_* staging tables for mutations
                                        |
                           Metadata persisted to s3://.../_meta/*.parquet
```

Data is stored as parquet files. Metadata (sync logs, table registry, column annotations) is persisted as small parquet files in a `_meta/` prefix. DuckDB's `httpfs` extension reads everything directly from cloud storage -- no local copies needed.

## Setup

### Amazon S3

```bash
# Set credentials
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=wJal...
export AWS_REGION=us-east-1

# Initialize with S3 storage
dinobase init --storage s3://my-bucket/dinobase/
```

### Google Cloud Storage

GCS uses S3-compatible HMAC keys for DuckDB access:

```bash
# Set HMAC credentials (create in GCS Console > Settings > Interoperability)
export GCS_HMAC_KEY_ID=GOOG...
export GCS_HMAC_SECRET=...

# Initialize with GCS storage
dinobase init --storage gs://my-bucket/dinobase/
```

### Azure Blob Storage

```bash
# Option 1: Connection string
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"

# Option 2: Account name + key
export AZURE_STORAGE_ACCOUNT_NAME=myaccount
export AZURE_STORAGE_ACCOUNT_KEY=...

# Initialize with Azure storage
dinobase init --storage az://my-container/dinobase/
```

### S3-compatible services (MinIO, Cloudflare R2)

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export S3_ENDPOINT=minio.example.com:9000

dinobase init --storage s3://my-bucket/dinobase/
```

## Using cloud storage

Once initialized, all commands work the same way:

```bash
# Add sources
dinobase add stripe --api-key sk_test_...

# Sync writes parquet directly to cloud storage
dinobase sync

# Queries read from cloud parquet via DuckDB views
dinobase query "SELECT * FROM stripe.customers LIMIT 5"

# Status shows storage location
dinobase status --pretty
```

## Environment variable mode

For containers and cloud deployments, you can skip `dinobase init` and configure everything via environment variables:

```bash
export DINOBASE_STORAGE_URL=s3://my-bucket/dinobase/
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=wJal...
export AWS_REGION=us-east-1
```

The `DINOBASE_STORAGE_URL` variable takes priority over any config file setting.

## Cloud layout

Dinobase organizes cloud storage like this:

```
s3://my-bucket/dinobase/
  _meta/                          # Metadata tables as parquet
    sync_log.parquet
    tables.parquet
    columns.parquet
    mutations.parquet
    live_rows.parquet
  _state/                         # dlt pipeline state (for incremental sync)
    dinobase_stripe/
      state.json
      schemas/...
  _locks/                         # Distributed sync locks
    stripe.json
  data/                           # Synced source data
    stripe/
      customers/_compacted.parquet
      charges/_compacted.parquet
    hubspot/
      contacts/_compacted.parquet
```

## Incremental sync

Pipeline state is persisted to cloud storage between syncs. This means:

- The first sync loads all data from the source API
- Subsequent syncs only load new/changed records (incremental)
- State survives server restarts and container redeployments

State is stored in `_state/dinobase_{source_name}/` as small JSON files.

## Distributed locking

When multiple processes share the same cloud bucket (e.g., multiple containers, cron jobs), Dinobase uses a lock file to prevent concurrent syncs of the same source:

- Before syncing, a lock file is written to `_locks/{source_name}.json`
- If another process holds the lock, the sync is skipped with a `"skipped"` status
- Locks have a TTL (default 10 minutes) — stale locks from crashed processes are automatically overwritten
- Different sources lock independently, so `stripe` and `hubspot` can sync concurrently

## Parquet compaction

After each sync, Dinobase automatically compacts parquet files. Multiple load files are merged into a single `_compacted.parquet` per table, and old files are deleted. No manual intervention needed.

## Mutations in cloud mode

Mutations (UPDATE/INSERT) work the same as in local mode. The `_live_*` staging tables live in-memory and overlay the cloud parquet data. When you confirm a mutation:

1. The change is written to the source API (e.g., Stripe, HubSpot)
2. The row is stored in an in-memory staging table for immediate read-after-write consistency
3. On the next sync, staging is cleared and the fresh data is written to cloud parquet

## Credential reference

| Provider | URL scheme | DuckDB extension | Environment variables |
|----------|-----------|-----------------|----------------------|
| **S3** | `s3://` | httpfs | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` |
| **GCS** | `gs://` | httpfs (S3-compat) | `GCS_HMAC_KEY_ID`, `GCS_HMAC_SECRET` |
| **Azure** | `az://` | azure | `AZURE_STORAGE_CONNECTION_STRING` or `AZURE_STORAGE_ACCOUNT_NAME` + `AZURE_STORAGE_ACCOUNT_KEY` |
| **S3-compatible** | `s3://` | httpfs | Same as S3 + `S3_ENDPOINT` |
