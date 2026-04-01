---
title: Architecture
description: How Dinobase is built -- DuckDB, dlt, MCP, and the sync engine.
---

## Overview

```
                    Agent (Claude, GPT, etc.)
                              |
                    +---------+---------+
                    |                   |
               MCP Server             CLI
               (FastMCP)         (Click commands)
                    |                   |
                    +---------+---------+
                              |
                        QueryEngine
                        (DuckDB SQL)
                              |
                 +------------+------------+
                 |            |            |
           SyncEngine    File views    Metadata
           (dlt + parquet)  (DuckDB)   (_dinobase.*)
```

## Core components

### DuckDB (query engine + storage)

[DuckDB](https://duckdb.org/) is an embedded analytical database. It:

- Reads parquet files natively from disk and S3
- Executes SQL with PostgreSQL-compatible syntax plus analytical extensions
- Stores metadata in internal tables (`_dinobase.*`)
- Creates views over file sources for zero-copy reads
- Runs in-process (no separate server)

The `.duckdb` file stores metadata and view definitions. Synced data lives in parquet files.

### dlt (sync engine)

[dlt](https://dlthub.com/) (data load tool) handles data ingestion:

- Verified sources for major SaaS APIs
- REST API connector via YAML configs (50+ sources)
- GraphQL connector with Relay-style pagination
- `sql_database` connector for any SQLAlchemy-compatible database
- `filesystem` connector for cloud storage
- Handles pagination, rate limiting, incremental loading
- Writes to parquet via DuckDB destination

### MCP (agent interface)

[MCP](https://modelcontextprotocol.io/) (Model Context Protocol) provides the agent tool-calling interface:

- FastMCP server with stdio transport
- Dynamic instructions computed from database state
- Seven tools: `query`, `list_sources`, `describe`, `confirm`, `confirm_batch`, `cancel`, `refresh`

### Click (CLI)

The CLI uses [Click](https://click.palletsprojects.com/) for command parsing. All data commands output JSON by default for agent consumption.

## Module structure

```
dinobase/
  __init__.py              # Package init
  __version__.py           # Version
  cli.py                   # CLI commands (Click)
  config.py                # YAML config management
  db.py                    # DinobaseDB (DuckDB wrapper)
  query/
    engine.py              # QueryEngine (execute, list, describe, live fetch)
    mutations.py           # MutationEngine (UPDATE/INSERT with preview/confirm)
  fetch/
    client.py              # LiveFetchClient (single-record API calls)
  sync/
    engine.py              # SyncEngine (dlt pipeline runner)
    scheduler.py           # SyncScheduler (concurrent, scheduled)
    registry.py            # Source registry (99 entries + parquet/csv)
    metadata.py            # API metadata extraction (Stripe, HubSpot, Postgres)
    yaml_source.py         # YAML-to-dlt translation for REST/GraphQL configs
    write_client.py        # Write-back to source APIs
    source_config.py       # YAML config loader for write endpoints
    sources/
      parquet.py           # File source handler (views)
      graphql.py           # GraphQL source with Relay pagination
      apis/                # 54 YAML source definitions
  mcp/
    server.py              # FastMCP server + tools
    __main__.py            # MCP entry point
```

## Data flow

### API source sync (local mode)

1. `SyncEngine.sync()` called with source name and config
2. Source function loaded from registry via `get_source()`
3. dlt pipeline created with DuckDB destination
4. Data loaded to parquet, tables created in source schema
5. Metadata extracted from source API (OpenAPI, Properties API, pg_catalog)
6. Annotations stored in `_dinobase.columns`
7. Sync logged in `_dinobase.sync_log`

### API source sync (cloud mode)

1. `SyncEngine.sync()` called with source name and config
2. Source function loaded from registry via `get_source()`
3. dlt pipeline created with **filesystem destination** (writes parquet to S3/GCS/Azure)
4. DuckDB views created over cloud parquet: `read_parquet('s3://.../*.parquet')`
5. `_live_*` staging tables created in-memory for mutation overlay
6. Metadata persisted to cloud as `_meta/*.parquet` files
7. On server restart, metadata is loaded from cloud and views are recreated

### File source add

1. Schema created in DuckDB
2. Files resolved (directory scan, glob, S3 URL)
3. DuckDB view created per file: `CREATE VIEW schema.table AS SELECT * FROM read_parquet('...')`
4. Basic metadata inferred from column names
5. Row counts computed

### Query execution

1. SQL received via CLI or MCP
2. `QueryEngine.execute()` checks if it's a mutation (UPDATE/INSERT)
3. Mutations are routed to `MutationEngine` for preview/confirm flow
4. For SELECTs, check if it's a single-record lookup on a stale source
5. If stale + ID lookup + YAML config exists: call source API directly (live fetch)
6. Otherwise: run on DuckDB (parquet data)
7. Results serialized to JSON-safe format with `_freshness` tag (`live` or `synced`)
8. Truncation applied if over `max_rows`

### Mutation execution

1. Agent sends UPDATE/INSERT via `query` tool
2. `MutationEngine` parses SQL, validates guardrails (no DELETE/DROP)
3. Engine generates preview (affected rows, per-row diffs)
4. Preview returned with `mutation_id` -- nothing executed yet
5. Agent calls `confirm(mutation_id)` to execute
6. Engine calls source API (write-back) AND updates local data
7. Everything logged in `_dinobase.mutations`

## Concurrency model

The sync scheduler uses a thread pool (`ThreadPoolExecutor`):

- Each source gets its own thread
- Each thread creates its own `DinobaseDB` connection (DuckDB supports concurrent readers)
- A lock prevents scheduling a source that's already syncing
- Default: 10 concurrent workers, configurable via `--max-workers`

## Design decisions

**Parquet over direct DB writes:** Data stays portable. Switch to cloud storage with `--storage s3://...` and the same queries work.

**DuckDB views for files:** Zero-copy reads mean file sources are instant. No sync step, no data duplication.

**Cloud-native storage:** When configured with cloud storage, DuckDB runs in-memory and reads parquet files directly from S3/GCS/Azure via the `httpfs` extension. No local disk needed. Metadata is persisted as small parquet files in a `_meta/` prefix.

**Registry-based sources:** Adding a source is a data entry, not a code change. The registry maps source names to dlt import paths and credential schemas.

**Dynamic MCP instructions:** The server computes instructions from actual database state. Agents know exactly what data is available without hardcoded docs.
