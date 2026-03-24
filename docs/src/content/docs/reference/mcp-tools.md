---
title: MCP Tools Reference
description: Detailed reference for the three MCP tools exposed by Dinobase's MCP server.
---

The Dinobase MCP server exposes three tools to agents.

## `query`

Execute a SQL query against the database.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sql` | string | Yes | -- | SQL query (DuckDB dialect). Reference tables as `schema.table`. |
| `max_rows` | integer | No | `200` | Max rows to return (1--10,000) |

### Response

**Success:**

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

## `list_sources`

List all connected data sources with their tables, row counts, and last sync time.

### Parameters

None.

### Response

```json
{
  "sources": [
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
      "last_sync": "2024-01-15 10:30:00"
    }
  ]
}
```

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

## Dynamic instructions

When the MCP server starts, it builds dynamic instructions from the current database state. These tell the agent what data is available and how to use the tools. The instructions update when the server restarts or data changes.
