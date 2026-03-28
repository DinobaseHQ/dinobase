"""Dinobase tools for CrewAI agents."""

from __future__ import annotations

import json

from crewai.tools import tool

from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine

_db: DinobaseDB | None = None
_engine: QueryEngine | None = None


def _get_engine() -> QueryEngine:
    global _db, _engine
    if _engine is None:
        _db = DinobaseDB()
        _engine = QueryEngine(_db)
    return _engine


@tool("dinobase_query")
def dinobase_query(sql: str, max_rows: int = 200) -> str:
    """Execute a SQL query against Dinobase (DuckDB dialect).

    Use this to query business data synced from SaaS APIs, databases, and files.
    Tables are referenced as schema.table (e.g., stripe.customers, hubspot.contacts).
    Supports cross-source JOINs via shared columns like email or company name.

    Args:
        sql: SQL query to execute (DuckDB dialect).
        max_rows: Maximum rows to return (default 200, max 10000).
    """
    engine = _get_engine()
    result = engine.execute(sql, max_rows=max_rows)
    return json.dumps(result, indent=2, default=str)


@tool("dinobase_list_sources")
def dinobase_list_sources() -> str:
    """List all connected Dinobase data sources with tables, row counts, and freshness.

    Use this first to understand what business data is available before writing queries.
    """
    engine = _get_engine()
    result = engine.list_sources()
    return json.dumps(result, indent=2, default=str)


@tool("dinobase_describe")
def dinobase_describe(table: str) -> str:
    """Describe a Dinobase table's columns, types, annotations, and sample data.

    Use this before writing queries to understand column names and types.

    Args:
        table: Table reference as schema.table (e.g., stripe.customers) or just table name.
    """
    engine = _get_engine()
    result = engine.describe_table(table)
    return json.dumps(result, indent=2, default=str)


@tool("dinobase_refresh")
def dinobase_refresh(source_name: str) -> str:
    """Re-sync a Dinobase data source to get fresh data.

    Use this when data might be stale and you need up-to-date results.

    Args:
        source_name: Name of the source to refresh (e.g., stripe, hubspot).
    """
    from dinobase.config import get_sources
    from dinobase.sync.engine import SyncEngine

    sources = get_sources()
    if source_name not in sources:
        return json.dumps({"error": f"Source '{source_name}' not found. Available: {', '.join(sources.keys())}"})

    config = sources[source_name]
    if config.get("type") in ("parquet", "csv"):
        return json.dumps({"error": "File sources read live data — no refresh needed."})

    engine = _get_engine()
    sync_engine = SyncEngine(engine.db)
    result = sync_engine.sync(source_name, config)
    freshness = engine.get_freshness(source_name)

    return json.dumps({
        "source": source_name,
        "status": result.status,
        "tables_synced": result.tables_synced,
        "rows_synced": result.rows_synced,
        "error": result.error,
        "freshness": freshness,
    }, indent=2, default=str)


# Convenience list for importing all tools at once
all_tools = [dinobase_query, dinobase_list_sources, dinobase_describe, dinobase_refresh]
