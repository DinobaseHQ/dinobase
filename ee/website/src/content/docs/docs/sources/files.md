---
title: File Sources
description: Use parquet and CSV files as data sources -- local files, S3, or GCS with zero sync.
---

File sources are the simplest way to get data into Dinobase. No sync needed -- DuckDB reads files directly at query time through views.

## Adding file sources

### Parquet files

```bash
# Directory of parquet files
dinobase add parquet --path ./data/events/ --name analytics

# Single file
dinobase add parquet --path ./data/export.parquet --name export

# Glob pattern
dinobase add parquet --path "./data/*.parquet" --name data

# S3
dinobase add parquet --path s3://your-bucket/exports/ --name warehouse

# GCS
dinobase add parquet --path gs://your-bucket/data/ --name warehouse
```

### CSV files

```bash
# Directory of CSV files
dinobase add csv --path ./exports/ --name reports

# Single CSV
dinobase add csv --path ./data/customers.csv --name customers
```

## How it works

When you add a file source, Dinobase:

1. Creates a schema with the name you provide
2. Scans the path for matching files
3. Creates a DuckDB **view** for each file
4. The view references the file directly -- no data is copied

Each file becomes a table named after its filename:

| File | Table name |
|------|-----------|
| `customers.parquet` | `customers` |
| `event-log.parquet` | `event_log` |
| `2024_orders.csv` | `2024_orders` |

## Path resolution

| Input | Behavior |
|-------|----------|
| Directory (`./data/`) | Finds all matching files, including subdirectories |
| Single file (`./data/events.parquet`) | Creates one table |
| Glob pattern (`./data/*.parquet`) | Matches files by pattern |
| S3 URL (`s3://bucket/prefix/`) | DuckDB reads from S3 at query time |
| GCS URL (`gs://bucket/prefix/`) | DuckDB reads from GCS at query time |

For directories, Dinobase first looks for files in the top level, then searches recursively if none are found.

## Remote files (S3, GCS)

DuckDB can read parquet files directly from S3 and GCS. The data is fetched at query time -- nothing is stored locally.

```bash
dinobase add parquet --path s3://my-data-lake/exports/ --name lake
dinobase query "SELECT COUNT(*) FROM lake.events" --pretty
```

For S3, DuckDB uses your AWS credentials from the environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) or from `~/.aws/credentials`.

## Schema annotations

File sources get basic metadata inferred from column names:

- `id` columns are marked as primary keys
- `*_id` columns are annotated as foreign keys
- `email` columns are marked as join keys
- Timestamp columns (`created_at`, etc.) are labeled

```bash
dinobase describe analytics.events --pretty
```

## No sync needed

File sources never appear in `dinobase sync` output. They are always read at query time, so the data is always current:

```bash
# Update the file
cp new_data.parquet ./data/events.parquet

# Query reflects the new data immediately
dinobase query "SELECT COUNT(*) FROM analytics.events"
```

## When to use file sources vs cloud storage sync

| | File sources | Cloud storage sync |
|--|-------------|-------------------|
| **Command** | `dinobase add parquet --path ...` | `dinobase add s3 --bucket-url ...` |
| **Sync** | None -- reads at query time | dlt syncs incrementally |
| **Best for** | Static exports, local files, S3/GCS parquet | Incrementally growing file sets |
| **Data location** | Stays in place | Copied to `~/.dinobase/` |
