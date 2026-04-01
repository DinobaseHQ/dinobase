---
title: Database Sources
description: Connect PostgreSQL, MySQL, Snowflake, BigQuery, and other databases to Dinobase.
---

Database sources use dlt's `sql_database` connector, which supports any SQLAlchemy-compatible database. Data is synced to parquet and queryable alongside your other sources.

## General usage

```bash
dinobase add <type> --connection-string <url>
dinobase sync
```

Credentials can also be set via the `DATABASE_URL` environment variable.

## Supported databases

### PostgreSQL

```bash
dinobase add postgres --connection-string postgresql://user:pass@host:5432/dbname
```

**Metadata:** Column comments and foreign key relationships extracted from `pg_catalog`.

### MySQL

```bash
dinobase add mysql --connection-string mysql://user:pass@host:3306/dbname
```

### MariaDB

MySQL-compatible.

```bash
dinobase add mariadb --connection-string mysql://user:pass@host:3306/dbname
```

### Microsoft SQL Server

```bash
dinobase add mssql --connection-string mssql+pyodbc://user:pass@host/dbname
```

Requires: `pip install pyodbc`

### Oracle

```bash
dinobase add oracle --connection-string oracle://user:pass@host:1521/service
```

Requires: `pip install cx_Oracle`

### SQLite

```bash
dinobase add sqlite --path /path/to/database.db
```

### Snowflake

```bash
dinobase add snowflake --connection-string snowflake://user:pass@account/db/schema
```

Requires: `pip install snowflake-sqlalchemy`

### Google BigQuery

```bash
dinobase add bigquery --connection-string bigquery://project/dataset
```

Requires: `pip install sqlalchemy-bigquery`

### Amazon Redshift

```bash
dinobase add redshift --connection-string redshift+psycopg2://user:pass@host:5439/db
```

Requires: `pip install sqlalchemy-redshift`

### ClickHouse

```bash
dinobase add clickhouse --connection-string clickhouse://user:pass@host:8123/db
```

Requires: `pip install clickhouse-sqlalchemy`

### CockroachDB

PostgreSQL-compatible.

```bash
dinobase add cockroachdb --connection-string postgresql://user:pass@host:26257/db
```

### Databricks

```bash
dinobase add databricks --connection-string databricks://token:TOKEN@host:443/db
```

Requires: `pip install databricks-sql-connector`

### Trino

```bash
dinobase add trino --connection-string trino://user@host:8080/catalog/schema
```

Requires: `pip install trino`

### PrestoDB

```bash
dinobase add presto --connection-string presto://user@host:8080/catalog/schema
```

Requires: `pip install pyhive`

### DuckDB (external file)

```bash
dinobase add duckdb_source --connection-string duckdb:///path/to/file.duckdb
```

## Connection string format

Connection strings follow SQLAlchemy format:

```
dialect+driver://username:password@host:port/database
```

Examples:

```
postgresql://admin:secret@db.example.com:5432/myapp
mysql://root:pass@localhost:3306/analytics
snowflake://user:pass@xy12345.us-east-1/MYDB/PUBLIC
```

## Syncing databases

Database sources sync all user tables by default. After syncing, tables are accessible as `source_name.table_name`:

```bash
dinobase add postgres --connection-string ... --name production
dinobase sync
dinobase query "SELECT * FROM production.users LIMIT 5" --pretty
```
