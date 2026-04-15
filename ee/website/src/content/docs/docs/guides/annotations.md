---
title: Semantic Layer & Annotations
description: How Dinobase builds and maintains a semantic layer so agents understand your data without guessing.
---

Agents need to understand data, not just query it. Dinobase builds a **semantic layer** on top of synced data — table descriptions, column documentation, PII flags, and relationship graphs — so agents can write correct SQL without hallucinating field meanings or missing join paths.

## How it works

When you sync a connector, Dinobase automatically:

1. Loads data via dlt
2. Fetches column-level metadata from the upstream API (descriptions, enum values, format hints)
3. Detects foreign-key relationships from column name patterns (`*_id` → matching table)
4. If `ANTHROPIC_API_KEY` is set, runs a background Claude agent to fill remaining gaps with table descriptions, column docs, and PII flags
5. Stores everything in `_dinobase.{tables,columns,relationships,metadata}` and surfaces it through `describe`

The agent runs in the background — sync finishes immediately.

## Automatic relationship detection

After every sync, Dinobase scans column names and wires up relationships without any configuration:

- `customer_id` in `subscriptions` → `customers.id`
- `plan_id` in `subscriptions` → `plans.id`
- `_dlt_parent_id` in nested tables → parent table's `_dlt_id`

These relationships appear in `describe` as `related_tables`, so agents know exactly how to join across tables.

## Auto-annotation with Claude

Set `ANTHROPIC_API_KEY` and Dinobase will run a Claude agent after each sync to annotate everything the heuristics can't:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
dinobase sync stripe
# [semantic-agent] stripe: heuristic detected 3 relationship(s)
# [semantic-agent] stripe: running Claude annotation...
# [semantic-agent] stripe: annotation complete
```

Claude audits what's already annotated, then fills only the gaps:
- Table descriptions ("All Stripe customer accounts")
- Column descriptions ("Customer's billing email address")
- PII flags on email, name, phone, IP, and user-identifying fields
- Any relationships the heuristic missed

Already-annotated connectors are skipped automatically — re-syncing the same connector doesn't re-annotate.

The daemon uses a built-in agent loop that calls the Anthropic API directly — no `claude` CLI required. This makes it work equally in local dev, Docker containers, and cloud workers.

For manual annotation in Claude Code, use the skill: `/indexing-semantic-layer stripe`. The skill and the daemon implement the same logic; the daemon just runs it in-process without spawning a subagent subprocess.

### Disable auto-annotation

```bash
export DINOBASE_AUTO_ANNOTATE=false
dinobase sync stripe   # fast — no annotation step
```

## Manual annotation

Annotate any table or column yourself:

```bash
# Table description
dinobase annotate stripe.customers description "All Stripe customer accounts"

# Column description
dinobase annotate stripe.customers.email description "Customer's billing email"

# PII flag
dinobase annotate stripe.customers.email pii true

# Custom owner tag
dinobase annotate stripe.customers owner "billing-team"

# Relationship
dinobase annotate stripe.subscriptions customer_id stripe.customers id \
  --cardinality one_to_many \
  --description "Each subscription belongs to one customer"
```

Or pass a JSON array to annotate many things at once:

```bash
dinobase annotate '[
  {"target": "stripe.customers", "key": "description", "value": "All Stripe customer accounts"},
  {"target": "stripe.customers.email", "key": "pii", "value": "true"},
  {"from_table": "stripe.subscriptions", "from_column": "customer_id",
   "to_table": "stripe.customers", "to_column": "id",
   "cardinality": "one_to_many", "description": "Each subscription belongs to one customer"}
]'
```

Run `dinobase annotate --input-schema` to see the full JSON schema.

## Connector-specific metadata (from API)

Dinobase also fetches structured metadata from upstream APIs at sync time:

### Stripe

**Source:** [Stripe OpenAPI spec](https://github.com/stripe/openapi)

Extracts:
- Field descriptions (e.g., "Unique identifier for the object")
- Type annotations (e.g., `unix-time` format)
- Enum values (e.g., subscription status: `active`, `past_due`, `canceled`)

Example from `dinobase describe stripe.customers --pretty`:

```
stripe.customers (180 rows)
Description: All Stripe customer accounts

  id          VARCHAR   -- Unique identifier for the object.
  email       VARCHAR   -- Customer's billing email address. [PII]
                          Can be null
  created     INTEGER   -- Time at which the object was created.
                          Unix timestamp. Use to_timestamp() to convert.
  currency    VARCHAR   -- Three-letter ISO code for the currency
  delinquent  BOOLEAN   -- Whether the customer has an overdue invoice.

Related tables:
  stripe.subscriptions  (customer_id → id, one_to_many)
  stripe.charges        (customer_id → id, one_to_many)
```

### HubSpot

**Source:** HubSpot Properties API

Fetches live property metadata from your portal:
- Property labels and descriptions
- Enum options with human-readable labels
- Custom properties and calculated fields

### PostgreSQL

**Source:** `pg_catalog` system tables

- Column comments (`COMMENT ON COLUMN ...`)
- Foreign key constraints → automatically converted to relationships

## Querying the semantic layer

Inspect annotations directly with SQL:

```bash
# Tables with and without descriptions
dinobase query "
  SELECT table_name, row_count,
    CASE WHEN description IS NOT NULL THEN '✓' ELSE '✗' END as described
  FROM _dinobase.tables
  WHERE schema_name = 'stripe'
  ORDER BY row_count DESC
" --pretty

# Relationship graph
dinobase query "
  SELECT from_table, from_column, to_table, to_column, cardinality
  FROM _dinobase.relationships
  WHERE from_schema = 'stripe'
" --pretty

# PII columns
dinobase query "
  SELECT schema_name, table_name, column_name
  FROM _dinobase.metadata
  WHERE key = 'pii' AND value = 'true'
" --pretty
```

## How agents use the semantic layer

When an agent calls `describe`, it gets the full semantic context:

```json
{
  "schema": "stripe",
  "table": "subscriptions",
  "description": "Active and historical customer subscriptions",
  "columns": [
    {
      "name": "customer_id",
      "type": "VARCHAR",
      "description": "References customers.id",
      "nullable": true
    },
    {
      "name": "status",
      "type": "VARCHAR",
      "description": "Subscription lifecycle state",
      "note": "Values: active, past_due, canceled, trialing, unpaid"
    }
  ],
  "related_tables": [
    {
      "table": "stripe.customers",
      "join": "ON subscriptions.customer_id = customers.id",
      "cardinality": "many_to_one"
    }
  ]
}
```

The agent knows the join path, the column semantics, and the enum values — no hallucinating, no guessing.
