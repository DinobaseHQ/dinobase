---
title: Configuration
description: Configuration file format, directory structure, and settings.
---

## Directory structure

Dinobase stores everything in `~/.dinobase/` by default:

```
~/.dinobase/
  config.yaml        # Source configuration
  dinobase.duckdb    # DuckDB database (metadata + synced data)
  connectors/        # User-defined local connector YAML configs
  cache/             # Cached JSON data from local connectors
```

Override with `DINOBASE_DIR`:

```bash
export DINOBASE_DIR=/path/to/custom/dir
```

## config.yaml

The main configuration file. Created by `dinobase init`, updated by `dinobase add`.

### Format

```yaml
# Optional: store data in cloud storage instead of locally
storage:
  url: "s3://my-bucket/dinobase/"

sources:
  stripe:
    type: stripe
    credentials:
      api_key: sk_live_...
    sync_interval: 1h
  hubspot:
    type: hubspot
    credentials:
      api_key: pat-na1-...
    sync_interval: 30m
    freshness_threshold: 1h
  analytics:
    type: parquet
    credentials:
      path: ./data/events/
      format: parquet
```

### Fields

**Storage (optional):**

| Field | Required | Description |
|-------|----------|-------------|
| `storage.url` | No | Cloud storage URL (e.g., `s3://bucket/dinobase/`, `gs://bucket/dinobase/`, `az://container/dinobase/`). When set, data is stored in cloud storage instead of locally. Can also be set via `DINOBASE_STORAGE_URL` env var. |

**Per source:**

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Source type (e.g., `stripe`, `postgres`, `parquet`) |
| `credentials` | Yes | Source-specific credentials |
| `sync_interval` | No | How often to sync (e.g., `30m`, `1h`) |
| `freshness_threshold` | No | Max age before data is considered stale (e.g., `1h`, `30m`). Defaults: `1h` for SaaS APIs, `6h` for databases. File sources are never stale. |

**Credential keys vary by source type:**

| Source type | Credential keys |
|------------|----------------|
| SaaS APIs | `api_key`, `token`, etc. |
| Databases | `connection_string` |
| File sources | `path`, `format` |

### Editing manually

You can edit `config.yaml` directly to:

- Change credentials
- Update sync intervals
- Remove sources
- Add sources manually

Changes take effect on the next `dinobase sync` or `dinobase serve`.

## Storage modes

### Local (default)

Data is stored in `dinobase.duckdb` alongside the config file. No additional setup needed.

### Cloud storage

When `storage.url` is configured, Dinobase uses an in-memory DuckDB that reads/writes parquet files to cloud storage. Metadata is persisted as parquet files in a `_meta/` prefix. See the [Cloud Storage Backend](/docs/guides/cloud-storage-backend/) guide for setup instructions.

Supported providers: Amazon S3, Google Cloud Storage, Azure Blob Storage, and S3-compatible services (MinIO, Cloudflare R2).

## DuckDB database

In local mode, `dinobase.duckdb` contains:

### User data schemas

Each source gets its own schema (e.g., `stripe`, `hubspot`). Tables within contain synced data or views over files.

### Metadata schema (`_dinobase`)

Internal tables for tracking sync state and column annotations:

**`_dinobase.sync_log`**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `source_name` | VARCHAR | Source name |
| `source_type` | VARCHAR | Source type |
| `started_at` | TIMESTAMP | Sync start time |
| `finished_at` | TIMESTAMP | Sync end time |
| `status` | VARCHAR | `running`, `success`, or `error` |
| `tables_synced` | INTEGER | Tables loaded |
| `rows_synced` | BIGINT | Rows loaded |
| `error_message` | VARCHAR | Error details (if failed) |

**`_dinobase.tables`**

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | VARCHAR | Source name |
| `schema_name` | VARCHAR | Schema name |
| `table_name` | VARCHAR | Table name |
| `row_count` | BIGINT | Row count at last sync |
| `last_sync` | TIMESTAMP | Last sync time |

**`_dinobase.columns`**

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | VARCHAR | Source name |
| `schema_name` | VARCHAR | Schema name |
| `table_name` | VARCHAR | Table name |
| `column_name` | VARCHAR | Column name |
| `column_type` | VARCHAR | DuckDB data type |
| `is_nullable` | BOOLEAN | Whether nullable |
| `description` | VARCHAR | Human-readable description |
| `note` | VARCHAR | Additional notes (format, enums, etc.) |

You can query these tables directly:

```bash
dinobase query "SELECT * FROM _dinobase.sync_log ORDER BY started_at DESC LIMIT 5" --pretty
dinobase query "SELECT * FROM _dinobase.columns WHERE description IS NOT NULL" --pretty
```
