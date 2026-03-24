---
title: Syncing & Scheduling
description: Sync data from API sources -- one-time, scheduled, or as a background daemon.
---

API sources (SaaS tools, databases) need to sync their data into Dinobase. File sources (parquet, CSV) skip syncing entirely -- DuckDB reads them at query time.

## One-time sync

```bash
# Sync all sources
dinobase sync

# Sync one source
dinobase sync stripe
```

Output shows progress per source:

```
  stripe: synced 4 tables (12,450 rows)
  hubspot: synced 3 tables (8,320 rows)

Done. 7 tables, 20,770 rows total.
```

## Scheduled sync (daemon mode)

Run Dinobase as a daemon that syncs on configured intervals:

```bash
# Default: check every minute, sync sources every 1 hour
dinobase sync --schedule

# Custom interval
dinobase sync --schedule --interval 30m

# Higher concurrency
dinobase sync --schedule --max-workers 20
```

The scheduler:

- Checks which sources are due for a sync every 60 seconds
- Syncs due sources concurrently (up to `--max-workers` at a time)
- Respects per-source intervals set during `dinobase add`
- Catches errors per-source without crashing
- Logs everything to stderr

### Per-source intervals

Each source can have its own sync interval:

```bash
dinobase add stripe --api-key ... --sync-interval 15m
dinobase add hubspot --api-key ... --sync-interval 1h
dinobase add postgres --connection-string ... --sync-interval 6h
```

The scheduler uses these intervals, falling back to the global `--interval` default.

Supported formats: `30s`, `5m`, `1h`, `6h`, `1d`.

## Background sync with MCP server

Run sync alongside the MCP server:

```bash
dinobase serve --sync --sync-interval 30m
```

This starts the MCP server and a background sync thread. Agents always query fresh data.

## Concurrent syncing

Sources sync in parallel using a thread pool. Each source gets its own dlt pipeline and database connection to avoid conflicts.

```bash
# Up to 20 sources syncing at once
dinobase sync --max-workers 20
```

Default is 10 concurrent workers. Increase for many sources; decrease if you hit API rate limits.

## What happens during sync

1. **dlt pipeline runs** -- fetches data from the source API, handles pagination and rate limiting
2. **Data writes to parquet** -- stored in `~/.dinobase/` as parquet files
3. **Metadata extraction** -- column descriptions fetched from source API (Stripe OpenAPI, HubSpot Properties API, Postgres catalog)
4. **Annotations stored** -- metadata saved to `_dinobase.columns` table
5. **Sync logged** -- start time, end time, status, table/row counts recorded in `_dinobase.sync_log`

## Monitoring syncs

```bash
# See last sync times and row counts
dinobase status --pretty
```

Sync history is stored in the `_dinobase.sync_log` table. You can query it directly:

```bash
dinobase query "
  SELECT source_name, status, tables_synced, rows_synced,
         started_at, finished_at, error_message
  FROM _dinobase.sync_log
  ORDER BY started_at DESC
  LIMIT 10
" --pretty
```

## File sources skip sync

File sources (parquet, CSV) create DuckDB views that read files at query time. They never appear in `dinobase sync` output:

```bash
dinobase add parquet --path ./data/ --name analytics  # instant, no sync
dinobase sync  # skips analytics, only syncs API sources
```
