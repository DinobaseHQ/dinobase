---
title: Syncing & Scheduling
description: Sync data from API connectors -- one-time, scheduled, or as a background daemon.
---

API connectors (SaaS tools, databases, MCP servers) need to sync their data into Dinobase. File connectors (parquet, CSV) skip syncing entirely -- DuckDB reads them at query time.

## One-time sync

```bash
# Sync all connectors
dinobase sync

# Sync one connector
dinobase sync stripe
```

Output shows progress per connector:

```
  stripe: synced 4 tables (12,450 rows)
  hubspot: synced 3 tables (8,320 rows)

Done. 7 tables, 20,770 rows total.
```

## Scheduled sync (daemon mode)

Run Dinobase as a daemon that syncs on configured intervals:

```bash
# Default: check every minute, sync connectors every 1 hour
dinobase sync --schedule

# Custom interval
dinobase sync --schedule --interval 30m

# Higher concurrency
dinobase sync --schedule --max-workers 20
```

The scheduler:

- Checks which connectors are due for a sync every 60 seconds
- Syncs due connectors concurrently (up to `--max-workers` at a time)
- Respects per-connector intervals set during `dinobase add`
- Catches errors per-connector without crashing
- Logs everything to stderr

### Per-connector intervals

Each connector can have its own sync interval:

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

Connectors sync in parallel using a thread pool. Each connector gets its own dlt pipeline and database connection to avoid conflicts.

```bash
# Up to 20 connectors syncing at once
dinobase sync --max-workers 20
```

Default is 10 concurrent workers. Increase for many connectors; decrease if you hit API rate limits.

## What happens during sync

1. **dlt pipeline runs** -- fetches data from the upstream API, handles pagination and rate limiting
2. **Data writes to parquet** -- stored in `~/.dinobase/` as parquet files
3. **Metadata extraction** -- column descriptions fetched from the upstream API (Stripe OpenAPI, HubSpot Properties API, Postgres catalog)
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

## Freshness thresholds

Each connector has a freshness threshold -- the maximum age before data is considered stale. The `list_connectors` MCP tool and `dinobase status` show freshness for each connector.

**Defaults:**

| Connector category | Default threshold |
|----------------|-------------------|
| SaaS APIs (Stripe, HubSpot, etc.) | `1h` |
| Databases (Postgres, MySQL, etc.) | `6h` |
| File connectors (parquet, CSV) | never stale |

**Override per connector:**

```bash
dinobase add stripe --api-key ... --freshness 30m
```

Or edit `config.yaml` directly:

```yaml
sources:
  stripe:
    type: stripe
    credentials: { api_key: sk_... }
    freshness_threshold: 30m
```

(The config key remains `sources:` for backwards compatibility.)

## Refreshing stale connectors

Use `dinobase refresh` to re-sync stale connectors:

```bash
dinobase refresh stripe          # refresh one connector
dinobase refresh --stale         # refresh all stale connectors
dinobase refresh --stale --pretty
```

The `refresh` MCP tool lets agents trigger re-syncs:

```
Agent: refresh("stripe")
→ Re-syncs stripe, returns new freshness info + row counts
```

## Live fetch for single records

When data is stale and the agent queries a single record by primary key, Dinobase automatically calls the upstream API instead of returning stale parquet data. This is fully transparent -- the agent just writes SQL.

```sql
-- If intercom data is stale, this triggers GET /contacts/12345 on the Intercom API
SELECT * FROM intercom.contacts WHERE id = '12345'
```

The response includes `"_freshness": "live"` so the agent knows it got real-time data:

```json
{
  "columns": ["id", "name", "email"],
  "rows": [{"id": "12345", "name": "Alice", "email": "alice@acme.com"}],
  "_freshness": "live",
  "_source": "intercom API"
}
```

**When live fetch triggers:**
- Connector data is stale (exceeds freshness threshold)
- Query is a simple `SELECT ... FROM schema.table WHERE id = 'value'`
- The connector has a YAML config in `sources/configs/`

**When it does NOT trigger:**
- Data is fresh (normal parquet query)
- Query has JOINs, multiple conditions, or aggregations
- Connector has no YAML config (e.g., custom dlt sources)
- API call fails (graceful fallback to parquet)

This covers 55 connectors with YAML configs including Intercom, Chargebee, Linear, Amplitude, and more.

## File connectors skip sync

File connectors (parquet, CSV) create DuckDB views that read files at query time. They never appear in `dinobase sync` output:

```bash
dinobase add parquet --path ./data/ --name analytics  # instant, no sync
dinobase sync  # skips analytics, only syncs API connectors
```
