---
title: Python API
description: Use Dinobase programmatically from Python -- DinobaseDB, QueryEngine, SyncEngine, and SyncScheduler.
---

Dinobase can be used as a Python library in addition to the CLI and MCP server.

## DinobaseDB

The core database class. Wraps DuckDB with metadata management.

```python
from dinobase.db import DinobaseDB

db = DinobaseDB()  # uses ~/.dinobase/dinobase.duckdb
# or
db = DinobaseDB("/path/to/custom.duckdb")
```

### Methods

#### `db.conn`

Property. Returns the DuckDB connection, creating it and initializing metadata tables on first access.

```python
conn = db.conn  # duckdb.DuckDBPyConnection
```

#### `db.query(sql)`

Execute SQL, return results as a list of dicts.

```python
rows = db.query("SELECT * FROM stripe.customers LIMIT 5")
# [{"id": "cus_123", "email": "alice@example.com", ...}, ...]
```

#### `db.query_raw(sql)`

Execute SQL, return `(column_names, rows)` tuple.

```python
columns, rows = db.query_raw("SELECT * FROM stripe.customers LIMIT 5")
# (["id", "email", ...], [("cus_123", "alice@example.com", ...), ...])
```

#### `db.get_schemas()`

List all user schemas (excludes internal ones).

```python
schemas = db.get_schemas()
# ["stripe", "hubspot"]
```

#### `db.get_tables(schema)`

List all tables in a schema.

```python
tables = db.get_tables("stripe")
# ["customers", "subscriptions", "charges", "invoices"]
```

#### `db.get_columns(schema, table)`

Get column info for a table.

```python
columns = db.get_columns("stripe", "customers")
# [{"column_name": "id", "data_type": "VARCHAR", "is_nullable": "YES"}, ...]
```

#### `db.get_row_count(schema, table)`

```python
count = db.get_row_count("stripe", "customers")
# 180
```

#### `db.log_sync_start(source_name, source_type)`

Record the start of a sync. Returns the sync log ID.

```python
sync_id = db.log_sync_start("stripe", "stripe")
```

#### `db.log_sync_end(sync_id, status, ...)`

Record the end of a sync.

```python
db.log_sync_end(sync_id, "success", tables_synced=4, rows_synced=1255)
db.log_sync_end(sync_id, "error", error_message="API rate limited")
```

#### `db.update_table_metadata(source_name, schema_name, annotations=None)`

Refresh `_dinobase.tables` and `_dinobase.columns` from actual schema. Optionally include annotations.

```python
annotations = {
    "customers": {
        "email": {"description": "Customer email", "note": "Join key"}
    }
}
db.update_table_metadata("stripe", "stripe", annotations=annotations)
```

#### `db.get_column_annotations(schema, table)`

Get stored annotations for a table's columns.

```python
anns = db.get_column_annotations("stripe", "customers")
# {"email": {"description": "The customer's email address.", "note": "Can be null"}}
```

#### `db.close()`

Close the database connection.

---

## QueryEngine

High-level query interface with formatted results.

```python
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine

db = DinobaseDB()
engine = QueryEngine(db)
```

### Methods

#### `engine.execute(sql, max_rows=200)`

Execute SQL, return formatted results.

```python
result = engine.execute("SELECT * FROM stripe.customers LIMIT 5")
# {"columns": [...], "rows": [...], "row_count": 5, "total_rows": 5}

# Check for errors
if "error" in result:
    print(result["error"])
```

#### `engine.list_sources()`

List all sources with tables and stats.

```python
info = engine.list_sources()
# {"sources": [{"name": "stripe", "tables": [...], "table_count": 4, ...}]}
```

#### `engine.describe_table(table_ref)`

Describe a table. Accepts `"schema.table"` or just `"table"`.

```python
desc = engine.describe_table("stripe.customers")
# {"schema": "stripe", "table": "customers", "columns": [...], "sample_rows": [...]}
```

---

## MutationEngine

Handles writes back to source systems via SQL.

```python
from dinobase.db import DinobaseDB
from dinobase.query.mutations import MutationEngine

db = DinobaseDB()
engine = MutationEngine(db)
```

### Methods

#### `engine.handle_sql(sql, max_affected_rows=50)`

Parse and preview one or more mutation statements. Returns a preview with `mutation_id`.

```python
result = engine.handle_sql("UPDATE stripe.customers SET name = 'Acme' WHERE id = 'cus_123'")
# {"mutation_id": "mut_...", "status": "pending_confirmation", "preview": {...}}
```

Multi-statement SQL is supported:

```python
result = engine.handle_sql("""
    UPDATE stripe.customers SET name = 'Acme' WHERE id = 'cus_123';
    INSERT INTO linear.issues (title) VALUES ('Follow up');
""")
# {"batch_id": "batch_...", "mutations": [...]}
```

#### `engine.confirm(mutation_id)`

Execute a pending mutation.

```python
result = engine.confirm("mut_abc123def456")
# {"status": "executed", "api_write_back": {...}, "local_update": {...}}
```

#### `engine.confirm_batch(mutation_ids)`

Execute multiple pending mutations.

```python
result = engine.confirm_batch(["mut_abc123", "mut_def456"])
# {"status": "batch_executed", "succeeded": 2, "failed": 0}
```

#### `engine.cancel(mutation_id)`

Cancel a pending mutation.

```python
result = engine.cancel("mut_abc123def456")
# {"status": "cancelled", "mutation_id": "mut_abc123def456"}
```

#### `engine.list_pending()`

List all pending mutations.

```python
pending = engine.list_pending()
# [{"mutation_id": "mut_...", "operation": "UPDATE", ...}]
```

---

## SyncEngine

Syncs a single source using dlt.

```python
from dinobase.db import DinobaseDB
from dinobase.sync.engine import SyncEngine

db = DinobaseDB()
engine = SyncEngine(db)

result = engine.sync("stripe", {"type": "stripe", "credentials": {"api_key": "sk_..."}})
# SyncResult(source_name="stripe", status="success", tables_synced=4, rows_synced=1255)
```

### SyncResult

```python
@dataclass
class SyncResult:
    source_name: str
    source_type: str
    tables_synced: int
    rows_synced: int
    status: str         # "success" or "error"
    error: str | None
```

---

## SyncScheduler

Scheduled syncing with concurrency.

```python
from dinobase.db import DinobaseDB
from dinobase.sync.scheduler import SyncScheduler

db = DinobaseDB()
scheduler = SyncScheduler(db, default_interval="1h", max_workers=10)
```

### Methods

#### `scheduler.sync_all_due()`

Sync all sources that are due. Returns list of result dicts.

```python
results = scheduler.sync_all_due()
```

#### `scheduler.run_loop(check_interval=60)`

Run the sync loop in the foreground. Blocks until interrupted.

```python
try:
    scheduler.run_loop()
except KeyboardInterrupt:
    pass
```

#### `scheduler.start_background(check_interval=60)`

Start sync loop in a background daemon thread.

```python
scheduler.start_background()
# ... do other work ...
scheduler.stop()
```

#### `scheduler.stop()`

Stop the background sync loop.
