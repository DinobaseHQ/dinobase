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
- Six tools: `query`, `list_sources`, `describe`, `confirm`, `confirm_batch`, `cancel`

### Click (CLI)

The CLI uses [Click](https://click.palletsprojects.com/) for command parsing. All data commands output JSON by default for agent consumption.

## Module structure

```
src/dinobase/
  __init__.py              # Package init
  __version__.py           # Version
  cli.py                   # CLI commands (Click)
  config.py                # YAML config management
  db.py                    # DinobaseDB (DuckDB wrapper)
  query/
    engine.py              # QueryEngine (execute, list, describe)
    mutations.py           # MutationEngine (UPDATE/INSERT with preview/confirm)
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

### API source sync

1. `SyncEngine.sync()` called with source name and config
2. Source function loaded from registry via `get_source()`
3. dlt pipeline created with DuckDB destination
4. Data loaded to parquet, tables created in source schema
5. Metadata extracted from source API (OpenAPI, Properties API, pg_catalog)
6. Annotations stored in `_dinobase.columns`
7. Sync logged in `_dinobase.sync_log`

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
4. SELECT queries run on DuckDB directly
5. Results serialized to JSON-safe format
6. Truncation applied if over `max_rows`
7. Result returned with columns, rows, and metadata

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

**Parquet over direct DB writes:** Data stays portable. Swap `~/.dinobase/data/` for `s3://managed-bucket/` and the same queries work.

**DuckDB views for files:** Zero-copy reads mean file sources are instant. No sync step, no data duplication.

**Registry-based sources:** Adding a source is a data entry, not a code change. The registry maps source names to dlt import paths and credential schemas.

**Dynamic MCP instructions:** The server computes instructions from actual database state. Agents know exactly what data is available without hardcoded docs.
