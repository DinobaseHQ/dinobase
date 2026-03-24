---
title: Schema Annotations
description: How Dinobase extracts and surfaces column metadata so agents understand the data.
---

Agents need to understand data, not just query it. Dinobase extracts column-level metadata from source APIs at sync time and surfaces it through `describe`.

## How it works

When you sync a source, Dinobase:

1. Loads data via dlt
2. Fetches metadata from the source's API
3. Stores annotations in the `_dinobase.columns` table
4. Serves them through `describe` (CLI and MCP)

Metadata is always current -- it comes from the source of truth, not hardcoded mappings.

## Source-specific metadata

### Stripe

**Source:** [Stripe OpenAPI spec](https://github.com/stripe/openapi)

Dinobase fetches Stripe's public OpenAPI spec and extracts:

- Field descriptions (e.g., "Unique identifier for the object")
- Type annotations (e.g., `unix-time` format)
- Enum values (e.g., subscription status: `active`, `past_due`, `canceled`)
- Nullability

Example output from `dinobase describe stripe.customers --pretty`:

```
stripe.customers (180 rows)

  id          VARCHAR   -- Unique identifier for the object.
  email       VARCHAR   -- The customer's email address.
                          Can be null
  created     INTEGER   -- Time at which the object was created.
                          Unix timestamp. Use to_timestamp() to convert.
  currency    VARCHAR   -- Three-letter ISO code for the currency
  delinquent  BOOLEAN   -- Whether the customer has an overdue invoice.
```

The agent knows `created` is a Unix timestamp that needs `to_timestamp()` -- because Stripe's spec says so.

### HubSpot

**Source:** [HubSpot Properties API](https://developers.hubspot.com/docs/api/crm/properties)

Fetches live property metadata from the user's HubSpot portal:

- Property labels and descriptions
- Enum options with human-readable labels
- Custom properties (marked as "Custom property")
- Calculated fields with formulas
- Date/datetime format hints

### PostgreSQL

**Source:** `pg_catalog` system tables

Extracts from the database itself:

- Column comments (`COMMENT ON COLUMN ...`)
- Foreign key relationships (e.g., "Foreign key -> orders.id")

### File sources (parquet, CSV)

**Source:** Column inference from names and types

Basic annotations inferred from column names:

- `id` -- marked as primary key
- `*_id` -- marked as foreign key with table reference inferred
- `email` -- marked as "Potential join key across sources"
- `created_at`, `updated_at` -- labeled as timestamps

## Querying annotations directly

Annotations are stored in `_dinobase.columns`:

```bash
dinobase query "
  SELECT table_name, column_name, description, note
  FROM _dinobase.columns
  WHERE description IS NOT NULL
  ORDER BY table_name, column_name
" --pretty
```

## How agents use annotations

When an agent calls `describe`, it gets structured column info:

```json
{
  "columns": [
    {
      "name": "created",
      "type": "INTEGER",
      "nullable": true,
      "description": "Time at which the object was created.",
      "note": "Unix timestamp (seconds since epoch). Use to_timestamp() to convert."
    }
  ]
}
```

This tells the agent exactly how to handle the column -- no guessing, no hallucinating field meanings.
