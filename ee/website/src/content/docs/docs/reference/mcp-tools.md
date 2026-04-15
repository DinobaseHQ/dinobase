---
title: MCP Tools Reference
description: Detailed reference for the eight MCP tools exposed by Dinobase's MCP server.
---

The Dinobase MCP server exposes eight tools to agents.

## `query`

Execute a SQL query against the database.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sql` | string | Yes | -- | SQL query (DuckDB dialect). Reference tables as `schema.table`. |
| `max_rows` | integer | No | `200` | Max rows to return (1--10,000) |

### Response

**Success (SELECT):**

```json
{
  "columns": ["email", "name", "created"],
  "rows": [
    {"email": "alice@example.com", "name": "Alice", "created": 1700000000}
  ],
  "row_count": 1,
  "total_rows": 1
}
```

**Mutation (UPDATE/INSERT) -- returns preview instead of executing:**

```json
{
  "mutation_id": "mut_abc123def456",
  "status": "pending_confirmation",
  "preview": {
    "operation": "UPDATE",
    "source": "stripe",
    "table": "customers",
    "rows_affected": 1,
    "changes": [{"id": "cus_123", "name": "Old Name → New Name"}],
    "side_effects": ["Will call API to update 1 record(s) in stripe"]
  },
  "confirm": "Call confirm with mutation_id 'mut_abc123def456' to execute"
}
```

Responses include a `_freshness` field: `"synced"` for parquet data, `"live"` when the record was fetched directly from the upstream API (happens automatically for single-record lookups on stale connectors).

**Truncated (more rows than `max_rows`):**

```json
{
  "columns": ["email"],
  "rows": [...],
  "row_count": 200,
  "total_rows": 1547,
  "truncated": true,
  "message": "Showing 200 of 1547 rows. Add LIMIT or a WHERE clause to narrow results."
}
```

**Error:**

```json
{
  "error": "Catalog Error: Table with name 'nonexistent' does not exist!"
}
```

---

## `list_connectors`

List all configured connectors with their tables, row counts, and last sync time.

### Parameters

None.

### Response

```json
{
  "connectors": [
    {
      "name": "stripe",
      "tables": [
        {"name": "customers", "rows": 180},
        {"name": "subscriptions", "rows": 145},
        {"name": "charges", "rows": 520},
        {"name": "invoices", "rows": 410}
      ],
      "table_count": 4,
      "total_rows": 1255,
      "last_sync": "2024-01-15 10:30:00",
      "age": "2h 15m",
      "freshness_threshold": "1h",
      "is_stale": true
    }
  ]
}
```

Freshness fields (`age`, `freshness_threshold`, `is_stale`) are included for API connectors. File connectors (parquet, CSV) omit these since they read live data.

---

## `describe`

Describe a table's columns, types, annotations, and sample rows.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table` | string | Yes | Table to describe (e.g., `stripe.customers` or `customers`) |

### Response

```json
{
  "schema": "stripe",
  "table": "customers",
  "row_count": 180,
  "columns": [
    {
      "name": "id",
      "type": "VARCHAR",
      "nullable": true,
      "description": "Unique identifier for the object."
    },
    {
      "name": "created",
      "type": "INTEGER",
      "nullable": true,
      "description": "Time at which the object was created.",
      "note": "Unix timestamp (seconds since epoch). Use to_timestamp() to convert."
    }
  ],
  "sample_rows": [
    {"id": "cus_ABC123", "email": "alice@example.com", "created": 1700000000}
  ]
}
```

**Error (table not found):**

```json
{
  "error": "Table 'nonexistent' not found in any schema"
}
```

If a close match exists, the error includes a suggestion:

```json
{
  "error": "Table 'stripe.customer' not found. Did you mean 'stripe.customers'?"
}
```

---

## `confirm`

Confirm and execute a pending mutation. Mutations (UPDATE/INSERT sent via `query`) return a preview -- call this with the `mutation_id` to actually execute it.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mutation_id` | string | Yes | The `mutation_id` from a pending mutation preview |

### Response

```json
{
  "status": "executed",
  "mutation_id": "mut_abc123def456",
  "operation": "UPDATE",
  "source": "stripe",
  "table": "customers",
  "api_write_back": {
    "total_rows": 1,
    "api_calls": 1,
    "succeeded": 1,
    "failed": 0
  },
  "local_update": {
    "method": "staging_table",
    "rows_upserted": 1
  }
}
```

---

## `confirm_batch`

Confirm and execute multiple pending mutations from a multi-statement SQL.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mutation_ids` | string[] | Yes | List of `mutation_id` values to confirm together |

### Response

```json
{
  "status": "batch_executed",
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "results": [...]
}
```

---

## `cancel`

Cancel a pending mutation without executing it.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mutation_id` | string | Yes | The `mutation_id` of a pending mutation to cancel |

### Response

```json
{
  "status": "cancelled",
  "mutation_id": "mut_abc123def456"
}
```

---

## `refresh`

Re-sync a connector to get fresh data. Use when data is stale before running queries.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source` | string | Yes | Name of the connector to re-sync (e.g., `stripe`, `hubspot`). The parameter is kept as `source` for backwards compatibility. |

### Response

```json
{
  "status": "success",
  "tables_synced": 4,
  "rows_synced": 12450,
  "error": null,
  "freshness": {
    "last_sync": "2024-01-15 12:45:00",
    "age_seconds": 5,
    "age_human": "5s",
    "threshold": 3600,
    "threshold_human": "1h",
    "is_stale": false
  }
}
```

---

---

## `exec_code`

Execute a Python script with full access to Dinobase internals and the MCP client API. Use this for complex data processing, calling MCP tools on connected servers, or anything easier in code than SQL.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | Yes | Python code to execute. Set `result = ...` to capture output. |

### Available imports

The following are available without any setup:

```python
from dinobase.mcp import call, tools, servers, search, instructions
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine
```

### Response

Returns the value of the `result` variable if set, serialized as JSON. If `result` is not set, returns `{"status": "ok"}`. Errors are returned as `{"error": "ExceptionType: message"}`.

### Examples

**Call an MCP tool on a connected server:**

```python
from dinobase.mcp import call

result = call("posthog_mcp.dashboards-get-all")
```

**Call a tool with arguments:**

```python
from dinobase.mcp import call

result = call("posthog_mcp.dashboard-get", id=1118504)
```

**Process data with Python before returning:**

```python
from dinobase.mcp import call

raw = call("posthog_mcp.dashboards-get-all")
names = [r["name"] for r in raw.get("structuredContent", {}).get("results", [])]
result = names
```

**Discover what tools are available:**

```python
from dinobase.mcp import servers, search

result = search("dashboard")
```

---

## Dynamic instructions

When the MCP server starts, it builds dynamic instructions from the current database state. These tell the agent what data is available and how to use the tools. The instructions update when the server restarts or data changes.
