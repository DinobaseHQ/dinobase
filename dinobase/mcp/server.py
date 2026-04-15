"""MCP server for Dinobase — exposes query, describe, and list_connectors tools."""

from __future__ import annotations

import json
import sys
import time
from typing import Annotated, Any

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from dinobase.annotations import AnnotationInput, RelationshipInput, apply_annotation, apply_relationship
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine


# ---------------------------------------------------------------------------
# Dynamic instructions — brief orientation, not a schema dump
# ---------------------------------------------------------------------------


def _has_mcp_proxy_servers() -> bool:
    """Return True if any connector YAML declares a `transport` section (MCP proxy)."""
    import yaml
    from dinobase.config import get_connectors_dir

    connectors_dir = get_connectors_dir()
    if not connectors_dir.is_dir():
        return False
    for path in connectors_dir.glob("*.yaml"):
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            if cfg and "transport" in cfg:
                return True
        except Exception:
            continue
    return False


def _build_instructions(engine: QueryEngine) -> str:
    """Build MCP instructions from the current database state."""
    connectors_info = engine.list_connectors()
    connectors = connectors_info.get("connectors", [])

    if not connectors:
        base = (
            "This is a Dinobase instance with no data loaded yet. "
            "The user needs to run `dinobase add <connector>` and `dinobase sync` first."
        )
        if not _has_mcp_proxy_servers():
            return base
        return (
            base
            + "\n\n"
            + "You also have connected MCP servers. Use `exec_code` to browse and call them:\n"
            + "  from dinobase.mcp import servers, search, call\n"
            + "  result = servers()                         # what is connected\n"
            + '  result = search("issue")                   # find tools across all servers\n'
            + '  result = call("linear_mcp.issues-list")    # call one'
        )

    lines = [
        "You have access to a Dinobase database — business data synced from multiple connectors "
        "into a single SQL database (DuckDB dialect).",
        "",
    ]

    lines.append("Connected connectors:")
    has_stale = False
    for connector in connectors:
        table_names = [t["name"] for t in connector["tables"]]
        line = (
            f"  {connector['name']}: {', '.join(table_names)} "
            f"({connector['total_rows']:,} rows total)"
        )
        if connector.get("is_stale"):
            line += f" — STALE (last sync: {connector.get('age', '?')} ago)"
            has_stale = True
        elif connector.get("age"):
            line += f" — fresh ({connector['age']} ago)"
        lines.append(line)
    lines.append("")

    lines.append("How to work with this database:")
    lines.append("1. Use `list_connectors` to see what data is available (includes freshness)")
    lines.append("2. Use `describe` on a table to see its columns, types, annotations, and sample data")
    lines.append("3. Use `query` to run SQL (DuckDB dialect, reference tables as schema.table)")
    lines.append("4. Use `exec_code` to run Python when a task needs chaining, discovery, or reshaping beyond SQL")
    if has_stale:
        lines.append("5. Use `refresh` to re-sync a stale connector before querying")
    lines.append("")
    lines.append(
        "Call `describe` on any table to see its columns, `related_tables` (join paths), "
        "and any annotations (description, metadata tags like pii/deprecated/owner)."
    )
    lines.append(
        "Use `annotate` to document tables and columns: descriptions, pii flags, "
        "deprecated status, owners, and relationships (join paths). "
        "All annotations are stored permanently and returned in every future describe() call."
    )

    # Remind agent to build the graph for connectors that don't have one yet
    no_graph = engine.db.get_connectors_without_relationships()
    if no_graph:
        lines.append("")
        lines.append(
            f"Semantic layer not built for: {', '.join(no_graph)}. "
            "Explore with describe(), then call annotate() to add descriptions and relationships."
        )
    if has_stale:
        lines.append("")
        lines.append(
            "Some connectors are stale. For bulk queries, use `refresh` to re-sync. "
            "For single-record lookups by ID on stale connectors, the system will "
            "automatically fetch live data from the upstream API."
        )

    # exec_code — general-purpose Python escape hatch, equal partner to `query`
    lines.append("")
    lines.append(
        "`exec_code` — run Python with full access to dinobase internals and every "
        "connected MCP server. Reach for it when a task needs more than one step:"
    )
    lines.append("  • Chain MCP calls (fetch a list, then look up each item)")
    lines.append('  • Discover what is available: servers(), search("pattern"), tools("server")')
    lines.append("  • Reshape query results with Python (group by computed keys, parse strings)")
    lines.append("  • Call MCP tools whose arguments depend on a query result")
    lines.append("")
    lines.append("API (import inside your code string — nothing is pre-imported):")
    lines.append("  from dinobase.mcp import call, tools, servers, search, instructions")
    lines.append("  from dinobase.db import DinobaseDB")
    lines.append("  from dinobase.query.engine import QueryEngine")
    lines.append('  result = call("server.tool", arg=value)   # call a tool')
    lines.append("  result = servers()                         # list connected MCP servers")
    lines.append('  result = search("dashboard")               # regex search all server tools')
    lines.append("")
    lines.append(
        "`query` and `exec_code` are complementary: use `query` for SQL over synced "
        "tables, use `exec_code` for everything else."
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
        try:
            r = httpx.get(
                f"{self.api_url}/api/v1/query/info",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("instructions", "")
        except Exception as e:
            raise  # let _create_server fall back to local

    def list_connectors(self) -> str:
        import httpx
        try:
            r = httpx.get(
                f"{self.api_url}/api/v1/sources/",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return json.dumps(r.json(), indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def describe(self, table: str) -> str:
        import httpx
        try:
            r = httpx.get(
                f"{self.api_url}/api/v1/query/describe/{table}",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return json.dumps(r.json(), indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def query(self, sql: str, max_rows: int) -> str:
        import httpx
        try:
            r = httpx.post(
                f"{self.api_url}/api/v1/query/",
                json={"sql": sql, "max_rows": max_rows},
                headers=self._headers(),
                timeout=120,
            )
            r.raise_for_status()
            return json.dumps(r.json(), indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def refresh(self, source: str) -> str:
        import httpx
        try:
            r = httpx.post(
                f"{self.api_url}/api/v1/sync/",
                json={"connector_name": source},
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
        except Exception as e:
            return json.dumps({"error": str(e)})

        job_ids = r.json().get("job_ids", [])
        job_id = job_ids[0] if job_ids else None

        if not job_id:
            return json.dumps({"status": "queued"})

        # Poll until done (max 2 minutes)
        for _ in range(60):
            time.sleep(2)
            try:
                jr = httpx.get(
                    f"{self.api_url}/api/v1/sync/jobs/{job_id}",
                    headers=self._headers(),
                    timeout=10,
                )
                if jr.status_code == 200:
                    job = jr.json()
                    if job.get("status") not in ("running", "pending"):
                        return json.dumps(job, indent=2, default=str)
            except Exception:
                pass

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
            connectors = engine.list_connectors().get("connectors", [])
        print("Dinobase MCP server ready (local mode).", file=sys.stderr)
        for s in connectors:
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
    def list_connectors() -> str:
        """List all connected data connectors with their tables, row counts, and last sync time."""
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "list_connectors", "server_mode": "hosted" if client else "local"})
        if client:
            return client.list_connectors()
        with DinobaseDB() as db:
            eng = QueryEngine(db)
            result = eng.list_connectors()
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
          cardinality — "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many" (default: "one_to_many")
          description — human-readable explanation

        Examples:
          annotate([{"target": "github.issues", "key": "description", "value": "All GitHub issues and PRs"}])
          annotate([{"target": "github.issues.body", "key": "pii", "value": "false"}])
          annotate([{"from_table": "stripe.subscriptions", "from_column": "customer_id", "to_table": "stripe.customers", "to_column": "id", "cardinality": "one_to_many", "description": "Each subscription belongs to one customer"}])
        """
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "annotate", "server_mode": "hosted" if client else "local"})
        with DinobaseDB() as db:
            results = []
            for item in items:
                if isinstance(item, AnnotationInput):
                    results.append(apply_annotation(db, item))
                else:
                    results.append(apply_relationship(db, item))
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
            result = MutationEngine(db).cancel(mutation_id)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def refresh(
        source: Annotated[str, Field(description="Name of the connector to re-sync (e.g. 'stripe', 'hubspot')")],
    ) -> str:
        """Re-sync a connector to get fresh data. Use when data is stale or you need up-to-date results before querying. This call blocks until sync completes (typically 10-60 seconds depending on the connector size)."""
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
        connectors_config = config.get("connectors", {})
        if source not in connectors_config:
            return json.dumps({"error": f"Connector '{source}' not found"})

        source_config = connectors_config[source]
        if source_config.get("type") in ("parquet", "csv"):
            return json.dumps({"error": f"File connector '{source}' reads live data — no sync needed"})

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
                "then call annotate() with relationship items to build the semantic graph."
            )

        return json.dumps(result, indent=2, default=str)

    @server.tool()
    def exec_code(
        code: Annotated[str, Field(description="Python code to execute. Assign your return value to `result` — if unset, the tool returns {\"status\": \"ok\"}.")],
    ) -> str:
        """Run Python with access to dinobase internals and every connected MCP server.

        Use this to chain MCP calls, reshape query results, or discover what tools
        are available. Complementary to `query`: use SQL for reads over synced tables,
        use `exec_code` for anything that needs more than one step.

        Available imports (import inside your code — nothing is pre-imported):
          from dinobase.mcp import call, tools, servers, search, instructions
          from dinobase.db import DinobaseDB
          from dinobase.query.engine import QueryEngine

        Assign your return value to `result`. State does not persist between calls.

        Examples:
          # Discover what's available
          from dinobase.mcp import servers, search
          result = {"servers": servers(), "dashboard_tools": search("dashboard")}

          # Chain MCP calls: fetch list, then look up each item
          from dinobase.mcp import call
          dashboards = call("posthog_mcp.dashboards-get-all")
          ids = [d["id"] for d in dashboards.get("structuredContent", {}).get("results", [])]
          result = [call("posthog_mcp.dashboard-get", id=i).get("structuredContent") for i in ids[:5]]

          # Combine SQL and an MCP call
          from dinobase.db import DinobaseDB
          from dinobase.query.engine import QueryEngine
          from dinobase.mcp import call
          with DinobaseDB() as db:
              rows = QueryEngine(db).execute("SELECT id FROM hubspot.companies LIMIT 10")["rows"]
          result = [call("clearbit_mcp.company-lookup", id=r["id"]) for r in rows]
        """
        from dinobase import telemetry
        telemetry.capture("mcp_tool_called", {"tool": "exec_code", "server_mode": "hosted" if client else "local"})

        namespace: dict[str, Any] = {"__builtins__": __builtins__}
        try:
            exec(code, namespace)
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

        # Return the value of 'result' if set, otherwise None
        output = namespace.get("result")
        if output is None:
            return json.dumps({"status": "ok"})
        try:
            return json.dumps(output, indent=2, default=str)
        except (TypeError, ValueError):
            return str(output)

    return server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_server(sync_schedule: bool = False, sync_interval: str = "1h"):
    """Start the MCP server on stdio."""
    global mcp
    print("Dinobase MCP server starting...", file=sys.stderr)

    sync_db = None
    scheduler = None
    if sync_schedule:
        from dinobase.sync.scheduler import SyncScheduler
        sync_db = DinobaseDB()
        scheduler = SyncScheduler(sync_db, default_interval=sync_interval)
        scheduler.start_background()
        print(f"Background sync scheduler started (interval: {sync_interval})", file=sys.stderr)

    mcp = _create_server()

    try:
        mcp.run(transport="stdio")
    finally:
        if scheduler:
            scheduler.stop()
        if sync_db:
            sync_db.close()
