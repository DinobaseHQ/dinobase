"""MCP server for Dinobase — exposes query, describe, and list_sources tools."""

from __future__ import annotations

import json
import sys
from typing import Annotated, Any

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine

# ---------------------------------------------------------------------------
# Database state
# ---------------------------------------------------------------------------

_db: DinobaseDB | None = None
_engine: QueryEngine | None = None


def _get_engine() -> QueryEngine:
    global _db, _engine
    if _engine is None:
        _db = DinobaseDB()
        _engine = QueryEngine(_db)
    return _engine


# ---------------------------------------------------------------------------
# Dynamic instructions — brief orientation, not a schema dump
# ---------------------------------------------------------------------------


def _build_instructions(engine: QueryEngine) -> str:
    """Build MCP instructions from the current database state.

    These should be brief — just enough for the agent to know what tools to use
    and what sources exist. Full schema is available on demand via describe().
    """
    sources_info = engine.list_sources()
    sources = sources_info.get("sources", [])

    if not sources:
        return (
            "This is a Dinobase instance with no data loaded yet. "
            "The user needs to run `dinobase add <source>` and `dinobase sync` first."
        )

    lines = [
        "You have access to a Dinobase database — business data synced from multiple sources "
        "into a single SQL database (DuckDB dialect).",
        "",
    ]

    # Source overview — names, table counts, row counts, freshness.
    lines.append("Connected sources:")
    has_stale = False
    for source in sources:
        table_names = [t["name"] for t in source["tables"]]
        line = (
            f"  {source['name']}: {', '.join(table_names)} "
            f"({source['total_rows']:,} rows total)"
        )
        if source.get("is_stale"):
            line += f" — STALE (last sync: {source.get('age', '?')} ago)"
            has_stale = True
        elif source.get("age"):
            line += f" — fresh ({source['age']} ago)"
        lines.append(line)
    lines.append("")

    # How to use the tools
    lines.append("How to work with this database:")
    lines.append("1. Use `list_sources` to see what data is available (includes freshness)")
    lines.append("2. Use `describe` on a table to see its columns, types, annotations, and sample data")
    lines.append("3. Use `query` to run SQL (DuckDB dialect, reference tables as schema.table)")
    if has_stale:
        lines.append("4. Use `refresh` to re-sync a stale source before querying")
    lines.append("")
    lines.append(
        "Cross-source joins work via shared columns. Use `describe` to find join keys — "
        "columns annotated as join keys or with matching names across sources (e.g., email)."
    )
    if has_stale:
        lines.append("")
        lines.append(
            "Some sources are stale. For bulk queries, use `refresh` to re-sync. "
            "For single-record lookups by ID on stale sources, the system will "
            "automatically fetch live data from the source API."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP server + tools — created lazily by run_server()
# ---------------------------------------------------------------------------

# Module-level reference, initialized in run_server()
mcp: FastMCP | None = None


def _create_server() -> FastMCP:
    """Create the FastMCP server with instructions computed from the current DB state."""
    engine = _get_engine()
    instructions = _build_instructions(engine)

    sources = engine.list_sources().get("sources", [])
    print("Dinobase MCP server ready.", file=sys.stderr)
    for s in sources:
        print(f"  {s['name']}: {s['table_count']} tables, {s['total_rows']:,} rows", file=sys.stderr)

    server = FastMCP("dinobase", instructions=instructions)

    @server.tool()
    def query(
        sql: Annotated[str, Field(description="SQL query to execute (DuckDB dialect). Reference tables as schema.table, e.g. salesforce.opportunities. For mutations (UPDATE/INSERT/DELETE), append --force to skip confirmation and execute immediately.")],
        max_rows: Annotated[int, Field(description="Maximum rows to return", ge=1, le=10000)] = 200,
    ) -> str:
        """Execute a SQL query against the database. Use `describe` first to understand table columns and data types. Mutations return a preview by default — append --force to the SQL to execute immediately, or call confirm() with the mutation_id."""
        eng = _get_engine()
        result = eng.execute(sql, max_rows=max_rows)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def list_sources() -> str:
        """List all connected data sources with their tables, row counts, and last sync time."""
        eng = _get_engine()
        result = eng.list_sources()
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def describe(
        table: Annotated[str, Field(description="Table to describe, e.g. 'salesforce.opportunities' or 'zendesk.tickets'")],
    ) -> str:
        """Describe a table's columns, types, annotations, and sample rows. Annotations include data format notes (e.g. 'amounts in cents') and join key hints."""
        eng = _get_engine()
        result = eng.describe_table(table)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def confirm(
        mutation_id: Annotated[str, Field(description="The mutation_id from a pending mutation to confirm and execute")],
    ) -> str:
        """Confirm and execute a pending mutation. Mutations (UPDATE/INSERT/DELETE) return a preview first — call this with the mutation_id to actually execute it. Alternatively, use --force in the SQL to skip this step."""
        from dinobase.query.mutations import MutationEngine
        eng = _get_engine()
        mutation_engine = MutationEngine(eng.db)
        result = mutation_engine.confirm(mutation_id)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def confirm_batch(
        mutation_ids: Annotated[list[str], Field(description="List of mutation_ids to confirm and execute together")],
    ) -> str:
        """Confirm and execute multiple pending mutations (for multi-statement SQL that spans sources)."""
        from dinobase.query.mutations import MutationEngine
        eng = _get_engine()
        mutation_engine = MutationEngine(eng.db)
        result = mutation_engine.confirm_batch(mutation_ids)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def cancel(
        mutation_id: Annotated[str, Field(description="The mutation_id of a pending mutation to cancel")],
    ) -> str:
        """Cancel a pending mutation without executing it."""
        from dinobase.query.mutations import MutationEngine
        eng = _get_engine()
        mutation_engine = MutationEngine(eng.db)
        result = mutation_engine.cancel(mutation_id)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def refresh(
        source: Annotated[str, Field(description="Name of the source to re-sync (e.g. 'stripe', 'hubspot')")],
    ) -> str:
        """Re-sync a source to get fresh data. Use when data is stale or you need up-to-date results before querying. This call blocks until sync completes (typically 10-60 seconds depending on the source size)."""
        from dinobase.config import load_config
        from dinobase.sync.engine import SyncEngine

        eng = _get_engine()

        # Look up source config
        config = load_config()
        sources_config = config.get("sources", {})
        if source not in sources_config:
            return json.dumps({"error": f"Source '{source}' not found"})

        source_config = sources_config[source]
        if source_config.get("type") in ("parquet", "csv"):
            return json.dumps({"error": f"File source '{source}' reads live data — no sync needed"})

        # Run sync
        sync_engine = SyncEngine(eng.db)
        sync_result = sync_engine.sync(source, source_config)

        # Get updated freshness
        freshness = eng.get_freshness(source)

        return json.dumps({
            "status": sync_result.status,
            "tables_synced": sync_result.tables_synced,
            "rows_synced": sync_result.rows_synced,
            "error": sync_result.error,
            "freshness": freshness,
        }, indent=2, default=str)

    return server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_server(sync_schedule: bool = False, sync_interval: str = "1h"):
    """Start the MCP server on stdio.

    Args:
        sync_schedule: If True, start background sync scheduler
        sync_interval: Default sync interval (e.g. '1h', '30m')
    """
    global mcp
    print("Dinobase MCP server starting...", file=sys.stderr)

    # Optionally start background sync scheduler
    scheduler = None
    if sync_schedule:
        from dinobase.sync.scheduler import SyncScheduler
        engine = _get_engine()
        scheduler = SyncScheduler(engine.db, default_interval=sync_interval)
        scheduler.start_background()
        print(f"Background sync scheduler started (interval: {sync_interval})", file=sys.stderr)

    mcp = _create_server()

    try:
        mcp.run(transport="stdio")
    finally:
        if scheduler:
            scheduler.stop()
