---
title: Querying Data
description: SQL patterns for cross-connector queries, joins, aggregations, and working with DuckDB.
---

Dinobase uses [DuckDB](https://duckdb.org/) as its query engine. All queries use DuckDB SQL syntax, which is PostgreSQL-compatible with extra analytical functions.

## Basics

Tables are referenced as `schema.table`:

```sql
SELECT * FROM stripe.customers LIMIT 10
```

### From the CLI

```bash
# JSON output (default, agent-friendly)
dinobase query "SELECT * FROM stripe.customers LIMIT 5"

# Human-readable table
dinobase query "SELECT * FROM stripe.customers LIMIT 5" --pretty

# Limit result size
dinobase query "SELECT * FROM hubspot.contacts" --max-rows 1000
```

### From MCP

Agents use the `query` tool:

```json
{
  "tool": "query",
  "arguments": {
    "sql": "SELECT * FROM stripe.customers LIMIT 5",
    "max_rows": 200
  }
}
```

## Cross-connector joins

The core power of Dinobase. Join tables from different connectors on shared columns:

### Two-connector join

```sql
SELECT s.email, s.name, h.company
FROM stripe.customers s
JOIN hubspot.contacts h ON s.email = h.email
```

### Three-connector join

```sql
SELECT
  s.email,
  h.company,
  d.amount,
  d.dealstage
FROM stripe.customers s
JOIN hubspot.contacts h ON s.email = h.email
JOIN hubspot.deals d ON h.id = d.contact_id
WHERE d.dealstage = 'closedwon'
ORDER BY d.amount DESC
```

### Finding join keys

Use `dinobase describe` to find columns that work as join keys. Dinobase annotates likely join columns:

```bash
dinobase describe stripe.customers --pretty
# Look for: email (marked as "Potential join key across connectors")
```

Common join patterns:

| Column | Connectors | Notes |
|--------|---------|-------|
| `email` | Most connectors | Best cross-connector join key |
| `*_id` | Within a connector | Foreign keys (e.g., `contact_id`) |
| `domain` | CRM connectors | Company matching |

## Aggregations

```sql
-- Count customers per company
SELECT h.company, COUNT(DISTINCT s.email) as customers
FROM stripe.customers s
JOIN hubspot.contacts h ON s.email = h.email
GROUP BY h.company
ORDER BY customers DESC
```

```sql
-- Revenue by deal stage
SELECT d.dealstage, SUM(d.amount) as total, COUNT(*) as deals
FROM hubspot.deals d
GROUP BY d.dealstage
ORDER BY total DESC
```

## Finding unmatched records

Use `LEFT JOIN` to find data in one connector but not another:

```sql
-- Stripe customers without a HubSpot contact
SELECT s.email, s.name
FROM stripe.customers s
LEFT JOIN hubspot.contacts h ON s.email = h.email
WHERE h.email IS NULL
```

## Working with timestamps

Stripe stores timestamps as Unix integers. Use DuckDB's `to_timestamp()`:

```sql
SELECT email, to_timestamp(created) as created_date
FROM stripe.customers
WHERE to_timestamp(created) > '2024-01-01'
ORDER BY created DESC
```

HubSpot uses ISO 8601 strings, which DuckDB handles natively:

```sql
SELECT email, createdate
FROM hubspot.contacts
WHERE createdate > '2024-01-01'
```

## DuckDB-specific features

DuckDB has powerful analytical functions beyond standard SQL:

### Window functions

```sql
SELECT email, amount,
  SUM(amount) OVER (ORDER BY created) as running_total
FROM stripe.charges
```

### List aggregation

```sql
SELECT company,
  LIST(email) as all_emails,
  COUNT(*) as contact_count
FROM hubspot.contacts
GROUP BY company
```

### Regex matching

```sql
SELECT email FROM stripe.customers
WHERE regexp_matches(email, '.*@gmail\.com$')
```

### Reading parquet directly

DuckDB can also query parquet files inline:

```sql
SELECT * FROM read_parquet('path/to/file.parquet') LIMIT 10
```

## Result truncation

By default, queries return up to 200 rows. If there are more, the result includes a `truncated` flag and `total_rows` count:

```json
{
  "rows": [...],
  "row_count": 200,
  "total_rows": 1547,
  "truncated": true,
  "message": "Showing 200 of 1547 rows. Add LIMIT or a WHERE clause to narrow results."
}
```

Use `--max-rows` (CLI) or the `max_rows` parameter (MCP) to adjust, up to 10,000.

## Mutations

UPDATE and INSERT statements sent through `query` are intercepted and routed to the mutation engine. Instead of executing immediately, they return a preview with a `mutation_id`. See the [Mutations guide](/docs/guides/mutations/) for details.

```bash
dinobase query "UPDATE stripe.customers SET name = 'Acme' WHERE id = 'cus_123'"
# Returns preview, not execution
dinobase confirm mut_abc123def456
# Now it executes
```

## Error handling

SQL errors are returned in the result rather than thrown:

```json
{
  "error": "Catalog Error: Table with name 'nonexistent' does not exist!"
}
```

Check for the `error` key before processing results.
