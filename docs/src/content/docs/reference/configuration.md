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
```

Override with `DINOBASE_DIR`:

```bash
export DINOBASE_DIR=/path/to/custom/dir
```

## config.yaml

The main configuration file. Created by `dinobase init`, updated by `dinobase add`.

### Format

```yaml
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
  analytics:
    type: parquet
    credentials:
      path: ./data/events/
      format: parquet
```

### Fields

**Per source:**

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Source type (e.g., `stripe`, `postgres`, `parquet`) |
| `credentials` | Yes | Source-specific credentials |
| `sync_interval` | No | How often to sync (e.g., `30m`, `1h`) |

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

## DuckDB database

`dinobase.duckdb` contains:

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
