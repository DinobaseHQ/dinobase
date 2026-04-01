"""MCP server for Dinobase — exposes query, describe, and list_sources tools."""

from __future__ import annotations

import json
import sys
import time
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from dinobase.annotations import AnnotationInput, RelationshipInput, apply_annotation, apply_relationship
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine


# ---------------------------------------------------------------------------
# Dynamic instructions — brief orientation, not a schema dump
# ---------------------------------------------------------------------------


def _build_instructions(engine: QueryEngine) -> str:
    """Build MCP instructions from the current database state."""
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

    lines.append("How to work with this database:")
    lines.append("1. Use `list_sources` to see what data is available (includes freshness)")
    lines.append("2. Use `describe` on a table to see its columns, types, annotations, and sample data")
    lines.append("3. Use `query` to run SQL (DuckDB dialect, reference tables as schema.table)")
    if has_stale:
        lines.append("4. Use `refresh` to re-sync a stale source before querying")
    lines.append("")
    lines.append(
        "Call `describe` on any table to see its columns, `related_tables` (join paths), "
        "and any annotations (description, metadata tags like pii/deprecated/owner)."
    )
    lines.append(
        "Use `annotate` to document tables and columns: descriptions, pii flags, "
        "deprecated status, owners. Use `annotate_relationships` to map join paths. "
        "Both are stored permanently and returned in every future describe() call."
    )

    # Remind agent to build the graph for sources that don't have one yet
    no_graph = engine.db.get_sources_without_relationships()
    if no_graph:
        lines.append("")
        lines.append(
            f"Semantic layer not built for: {', '.join(no_graph)}. "
            "Explore with describe(), then call annotate() and annotate_relationships() to document."
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
# Hosted service client — used when credentials.json contains an api_url
# ---------------------------------------------------------------------------


class _HostedClient:
    """Proxies MCP tool calls to the hosted Dinobase API.

    Used when `~/.dinobase/credentials.json` has an `api_url`, meaning the
    user has run `dinobase login` and is connected to the hosted service.
    """

    def __init__(self, api_url: str, access_token: str):
        self.api_url = api_url.rstrip("/")
        self.access_token = access_token

    def _headers(self) -> dict[str, str]:
        # Always get a fresh token — handles mid-session expiry in long-running MCP servers
        from dinobase.config import ensure_fresh_cloud_token
        token = ensure_fresh_cloud_token() or self.access_token
        return {"Authorization": f"Bearer {token}"}

    def get_instructions(self) -> str:
        import httpx
        r = httpx.get(
            f"{self.api_url}/api/v1/query/info",
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("instructions", "")

    def list_sources(self) -> str:
        import httpx
        r = httpx.get(
            f"{self.api_url}/api/v1/sources/",
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, default=str)

    def describe(self, table: str) -> str:
        import httpx
        r = httpx.get(
            f"{self.api_url}/api/v1/query/describe/{table}",
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, default=str)

    def query(self, sql: str, max_rows: int) -> str:
        import httpx
        r = httpx.post(
            f"{self.api_url}/api/v1/query/",
            json={"sql": sql, "max_rows": max_rows},
            headers=self._headers(),
            timeout=120,
        )
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, default=str)

    def refresh(self, source: str) -> str:
        import httpx
        # Trigger sync
        r = httpx.post(
            f"{self.api_url}/api/v1/sync/",
            json={"source_name": source},
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        job_ids = r.json().get("job_ids", [])
        job_id = job_ids[0] if job_ids else None

        if not job_id:
            return json.dumps({"status": "queued"})

        # Poll until done (max 2 minutes)
        for _ in range(60):
            time.sleep(2)
            jr = httpx.get(
                f"{self.api_url}/api/v1/sync/jobs/{job_id}",
                headers=self._headers(),
                timeout=10,
            )
            if jr.status_code == 200:
                job = jr.json()
                if job.get("status") not in ("running", "pending"):
                    return json.dumps(job, indent=2, default=str)

        return json.dumps({"status": "timeout", "job_id": job_id})


def _load_hosted_client() -> _HostedClient | None:
    """Return a _HostedClient if the user is logged in to the hosted service."""
    from dinobase.config import load_cloud_credentials, get_cloud_api_url, ensure_fresh_cloud_token

    creds = load_cloud_credentials()
    if not creds:
        return None

    api_url = creds.get("api_url") or get_cloud_api_url()
    access_token = ensure_fresh_cloud_token()
    if not access_token:
        return None

    return _HostedClient(api_url, access_token)


# ---------------------------------------------------------------------------
# MCP server + tools — created lazily by run_server()
# ---------------------------------------------------------------------------

mcp: FastMCP | None = None


def _create_server() -> FastMCP:
    """Create the FastMCP server, routing to hosted API or local DB as appropriate."""
    # Try hosted service first
    client = _load_hosted_client()
    if client:
        try:
            instructions = client.get_instructions()
            print("Dinobase MCP connected to hosted service.", file=sys.stderr)
            print(f"  API: {client.api_url}", file=sys.stderr)
        except Exception as e:
            print(
                f"Could not reach hosted service ({e}), falling back to local DB.",
                file=sys.stderr,
            )
            client = None

    if not client:
        with DinobaseDB() as db:
            engine = QueryEngine(db)
            instructions = _build_instructions(engine)
            sources = engine.list_sources().get("sources", [])
        print("Dinobase MCP server ready (local mode).", file=sys.stderr)
        for s in sources:
            print(f"  {s['name']}: {s['table_count']} tables, {s['total_rows']:,} rows", file=sys.stderr)

    server = FastMCP("dinobase", instructions=instructions)

    @server.tool()
    def query(
        sql: Annotated[str, Field(description="SQL query to execute (DuckDB dialect). Reference tables as schema.table, e.g. salesforce.opportunities. For mutations (UPDATE/INSERT/DELETE), append --force to skip confirmation and execute immediately.")],
        max_rows: Annotated[int, Field(description="Maximum rows to return", ge=1, le=10000)] = 200,
    ) -> str:
        """Execute a SQL query against the database. Use `describe` first to understand table columns and data types. Mutations return a preview by default — append --force to the SQL to execute immediately, or call confirm() with the mutation_id."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "query", "server_mode": "hosted" if client else "local"})
        if client:
            return client.query(sql, max_rows)
        with DinobaseDB() as db:
            eng = QueryEngine(db)
            result = eng.execute(sql, max_rows=max_rows)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def list_sources() -> str:
        """List all connected data sources with their tables, row counts, and last sync time."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "list_sources", "server_mode": "hosted" if client else "local"})
        if client:
            return client.list_sources()
        with DinobaseDB() as db:
            eng = QueryEngine(db)
            result = eng.list_sources()
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def describe(
        table: Annotated[str, Field(description="Table to describe, e.g. 'salesforce.opportunities' or 'zendesk.tickets'")],
    ) -> str:
        """Describe a table's columns, types, annotations, and sample rows. Annotations include data format notes (e.g. 'amounts in cents') and join key hints."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "describe", "server_mode": "hosted" if client else "local"})
        if client:
            return client.describe(table)
        with DinobaseDB() as db:
            eng = QueryEngine(db)
            result = eng.describe_table(table)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def annotate(
        items: Annotated[list[AnnotationInput | RelationshipInput], Field(description="One or more annotation or relationship items to store")],
    ) -> str:
        """Annotate tables, columns, or store relationships. Accepts a mixed list of annotations and relationships in a single call.

        Annotation item (use for table/column descriptions and metadata tags):
          target      — "schema.table" or "schema.table.column"
          key         — "description", "note" (column-only), "deprecated", "pii", "sensitive", "owner", or any custom key
          value       — tag value; use "true"/"false" for boolean flags

        Relationship item (use to map join paths between tables):
          from_table  — "schema.table" (table holding the foreign key)
          from_column — column name
          to_table    — "schema.table" (referenced table)
          to_column   — column name
          cardinality — "one_to_one" | "one_to_many" | "many_to_many" (default: "one_to_many")
          description — human-readable explanation

        Examples:
          annotate([{"target": "github.issues", "key": "description", "value": "All GitHub issues and PRs"}])
          annotate([{"target": "github.issues.body", "key": "pii", "value": "false"}])
          annotate([{"from_table": "stripe.subscriptions", "from_column": "customer_id", "to_table": "stripe.customers", "to_column": "id", "cardinality": "one_to_many", "description": "Each subscription belongs to one customer"}])
        """
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "annotate", "server_mode": "hosted" if client else "local"})
        eng = _get_engine()
        results = []
        for item in items:
            if isinstance(item, AnnotationInput):
                results.append(apply_annotation(eng.db, item))
            else:
                results.append(apply_relationship(eng.db, item))
        return json.dumps(results if len(results) > 1 else results[0] if results else {}, indent=2)

    @server.tool()
    def confirm(
        mutation_id: Annotated[str, Field(description="The mutation_id from a pending mutation to confirm and execute")],
    ) -> str:
        """Confirm and execute a pending mutation. Mutations (UPDATE/INSERT/DELETE) return a preview first — call this with the mutation_id to actually execute it. Alternatively, use --force in the SQL to skip this step."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "confirm", "server_mode": "hosted" if client else "local"})
        from dinobase.query.mutations import MutationEngine
        with DinobaseDB() as db:
            eng = QueryEngine(db)
            result = MutationEngine(db).confirm(mutation_id)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def confirm_batch(
        mutation_ids: Annotated[list[str], Field(description="List of mutation_ids to confirm and execute together")],
    ) -> str:
        """Confirm and execute multiple pending mutations (for multi-statement SQL that spans sources)."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "confirm_batch", "server_mode": "hosted" if client else "local"})
        from dinobase.query.mutations import MutationEngine
        with DinobaseDB() as db:
            eng = QueryEngine(db)
            result = MutationEngine(db).confirm_batch(mutation_ids)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def cancel(
        mutation_id: Annotated[str, Field(description="The mutation_id of a pending mutation to cancel")],
    ) -> str:
        """Cancel a pending mutation without executing it."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "cancel", "server_mode": "hosted" if client else "local"})
        from dinobase.query.mutations import MutationEngine
        with DinobaseDB() as db:
            eng = QueryEngine(db)
            result = MutationEngine(db).cancel(mutation_id)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def refresh(
        source: Annotated[str, Field(description="Name of the source to re-sync (e.g. 'stripe', 'hubspot')")],
    ) -> str:
        """Re-sync a source to get fresh data. Use when data is stale or you need up-to-date results before querying. This call blocks until sync completes (typically 10-60 seconds depending on the source size)."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "refresh", "source": source, "server_mode": "hosted" if client else "local"})
        if client:
            return client.refresh(source)

        # MCP may have started in local mode even though the user is logged in
        # (e.g. hosted service was briefly unreachable at startup). Try hosted
        # client dynamically so refresh always routes to the API when possible.
        _dynamic_client = _load_hosted_client()
        if _dynamic_client:
            return _dynamic_client.refresh(source)

        from dinobase.config import load_config
        from dinobase.sync.engine import SyncEngine

        config = load_config()
        sources_config = config.get("sources", {})
        if source not in sources_config:
            return json.dumps({"error": f"Source '{source}' not found"})

        source_config = sources_config[source]
        if source_config.get("type") in ("parquet", "csv"):
            return json.dumps({"error": f"File source '{source}' reads live data — no sync needed"})

        with DinobaseDB() as db:
            eng = QueryEngine(db)
            sync_result = SyncEngine(db).sync(source, source_config)
            freshness = eng.get_freshness(source)

        result: dict = {
            "status": sync_result.status,
            "tables_synced": sync_result.tables_synced,
            "rows_synced": sync_result.rows_synced,
            "error": sync_result.error,
            "freshness": freshness,
        }

        if sync_result.status == "success" and not eng.db.has_relationships(source):
            result["reminder"] = (
                f"No relationships mapped for '{source}' yet. "
                "Call describe() on its tables, identify join paths, "
                "then call annotate_relationships() to build the semantic graph."
            )

        return json.dumps(result, indent=2, default=str)

    return server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_server(sync_schedule: bool = False, sync_interval: str = "1h"):
    """Start the MCP server on stdio."""
    global mcp
    print("Dinobase MCP server starting...", file=sys.stderr)

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
