"""Dinobase toolset for Pydantic AI agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic_ai import Agent, FunctionToolset, RunContext

from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine


@dataclass
class DinobaseDeps:
    """Dependencies for Dinobase-powered agents."""

    engine: QueryEngine | None = field(default=None, repr=False)

    def get_engine(self) -> QueryEngine:
        if self.engine is None:
            db = DinobaseDB()
            self.engine = QueryEngine(db)
        return self.engine


# -- Toolset ------------------------------------------------------------------

dinobase_tools = FunctionToolset()


@dinobase_tools.tool
def dinobase_query(ctx: RunContext[DinobaseDeps], sql: str, max_rows: int = 200) -> str:
    """Execute a SQL query against Dinobase (DuckDB dialect).

    Use this to query business data from connected sources. Tables are
    referenced as schema.table (e.g., stripe.customers, hubspot.contacts).
    Cross-source JOINs work via shared columns like email.

    Args:
        sql: SQL query to execute (DuckDB dialect).
        max_rows: Maximum rows to return (default 200, max 10000).
    """
    engine = ctx.deps.get_engine()
    result = engine.execute(sql, max_rows=max_rows)
    return json.dumps(result, indent=2, default=str)


@dinobase_tools.tool
def dinobase_list_sources(ctx: RunContext[DinobaseDeps]) -> str:
    """List all connected Dinobase data sources with tables, row counts, and freshness.

    Use this first to understand what business data is available before writing queries.
    """
    engine = ctx.deps.get_engine()
    result = engine.list_sources()
    return json.dumps(result, indent=2, default=str)


@dinobase_tools.tool
def dinobase_describe(ctx: RunContext[DinobaseDeps], table: str) -> str:
    """Describe a table's columns, types, annotations, and sample data.

    Use this before writing queries to understand column names and types.

    Args:
        table: Table reference as schema.table (e.g., stripe.customers).
    """
    engine = ctx.deps.get_engine()
    result = engine.describe_table(table)
    return json.dumps(result, indent=2, default=str)


@dinobase_tools.tool
def dinobase_refresh(ctx: RunContext[DinobaseDeps], source_name: str) -> str:
    """Re-sync a data source to get fresh data.

    Use when data might be stale and you need up-to-date results.

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

    engine = ctx.deps.get_engine()
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


# -- Pre-configured agent -----------------------------------------------------

dinobase_agent = Agent(
    "anthropic:claude-sonnet-4-6",
    deps_type=DinobaseDeps,
    toolsets=[dinobase_tools],
    instructions=(
        "You are a data analyst with access to Dinobase — a SQL database "
        "containing business data synced from multiple SaaS tools.\n\n"
        "Workflow:\n"
        "1. Use dinobase_list_sources to see what data is available\n"
        "2. Use dinobase_describe on relevant tables to understand schemas\n"
        "3. Use dinobase_query to run SQL (DuckDB dialect, tables are schema.table)\n"
        "4. Present results clearly with your analysis"
    ),
)
