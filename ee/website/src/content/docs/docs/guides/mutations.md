---
title: Mutations
description: Reverse ETL via SQL — write data back to upstream systems with UPDATE and INSERT, using a preview/confirm flow to prevent accidental changes.
---

Dinobase mutations are the SQL interface to reverse ETL — write data back to upstream systems via UPDATE and INSERT. Every mutation uses a preview/confirm flow to prevent accidental changes.

## How it works

```
Agent writes SQL    →  Engine previews    →  Agent confirms    →  API + local update
UPDATE stripe...       "2 rows affected"     confirm(id)          Stripe API called
```

1. Agent sends an UPDATE or INSERT statement via `query` (CLI or MCP)
2. Engine parses the SQL, counts affected rows, generates a per-row diff
3. Returns a preview with a `mutation_id` -- nothing is executed yet
4. Agent reviews the preview and calls `confirm` with the `mutation_id`
5. Engine calls the connector's upstream API (write-back) AND updates local data

## Supported operations

`UPDATE`, `INSERT`, and `DELETE` are supported. Destructive DDL is blocked entirely: `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`. `DELETE` requires a `WHERE` clause — bulk deletes without a filter are rejected.

## CLI usage

### UPDATE

```bash
dinobase query "UPDATE stripe.customers SET name = 'Acme Inc' WHERE id = 'cus_123'"
```

Response (preview):

```json
{
  "mutation_id": "mut_abc123def456",
  "status": "pending_confirmation",
  "preview": {
    "operation": "UPDATE",
    "source": "stripe",
    "table": "customers",
    "rows_affected": 1,
    "changes": [
      {"id": "cus_123", "name": "Old Name → Acme Inc"}
    ],
    "side_effects": ["Will call API to update 1 record(s) in stripe"]
  }
}
```

Confirm to execute:

```bash
dinobase confirm mut_abc123def456
```

### INSERT

```bash
dinobase query "INSERT INTO linear.issues (title, team_id) VALUES ('Fix bug', 'team_123')"
```

Confirm:

```bash
dinobase confirm mut_def789abc012
```

### Cancel

```bash
dinobase cancel mut_abc123def456
```

## MCP usage

The same flow works through MCP tools:

1. Agent calls `query` with mutation SQL -- gets preview
2. Agent calls `confirm` with `mutation_id` -- executes
3. Or `cancel` to discard

For multi-statement mutations, use `confirm_batch`:

```sql
UPDATE stripe.customers SET name = 'Acme' WHERE id = 'cus_123';
INSERT INTO linear.issues (title) VALUES ('Follow up with Acme');
```

This returns multiple `mutation_id` values. Confirm all at once with `confirm_batch`.

## Guardrails

### Preview by default

Nothing executes until confirmed. The preview shows exactly what will change:

- Per-row diffs (`old value → new value`)
- Which upstream API will be called
- Number of affected rows

### Row limit

By default, mutations affecting more than 50 rows are blocked:

```json
{
  "error": "This UPDATE would affect 200 rows (limit: 50). Add a more specific WHERE clause."
}
```

### Audit log

Every mutation is recorded in `_dinobase.mutations`:

```bash
dinobase query "
  SELECT mutation_id, source_name, operation, status, created_at
  FROM _dinobase.mutations
  ORDER BY created_at DESC
  LIMIT 10
" --pretty
```

## Write-back

When a mutation is confirmed, Dinobase:

1. **Calls the upstream API** -- e.g., updates the Stripe customer via Stripe's API
2. **Updates local data** -- writes to a staging table for read-after-write consistency

Write-back requires the connector to have write endpoints defined in its YAML config. Connectors without write configs still update local data.

### Per-row API calls

For UPDATE operations, each affected row gets its own API call. Results are tracked per-row:

```json
{
  "api_write_back": {
    "total_rows": 3,
    "api_calls": 3,
    "succeeded": 3,
    "failed": 0
  }
}
```

### Bulk endpoints

Some connectors support bulk operations. When a write endpoint is marked as `bulk: true`, rows are batched into fewer API calls.

## Multi-statement mutations

Send multiple mutations in a single SQL string, separated by semicolons:

```sql
UPDATE stripe.customers SET name = 'Acme' WHERE id = 'cus_123';
INSERT INTO linear.issues (title, team_id) VALUES ('Update Acme account', 'team_abc');
```

The engine validates each statement independently and returns a batch preview. Use `confirm_batch` to execute all at once.
