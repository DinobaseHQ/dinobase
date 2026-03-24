"""CLI for Dinobase."""

from __future__ import annotations

import json
import sys

import click

from dinobase import __version__


@click.group()
@click.version_option(version=__version__)
def cli():
    """Dinobase — the agent-native database."""
    pass


@cli.command()
def init():
    """Initialize Dinobase (create config directory and database)."""
    from dinobase.config import init_dinobase, get_db_path

    ddir = init_dinobase()
    # Touch the database to create it
    from dinobase.db import DinobaseDB
    db = DinobaseDB()
    _ = db.conn  # triggers initialization
    db.close()

    click.echo(f"Dinobase initialized at {ddir}")
    click.echo(f"Database: {get_db_path()}")
    click.echo("Add a source: dinobase add <source> --api-key ...  (run `dinobase sources` to list all)")


@cli.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("source_type")
@click.option("--name", help="Custom name for the source (defaults to source type)")
@click.option("--path", help="Path to files (for parquet/csv sources)")
@click.pass_context
def add(ctx: click.Context, source_type: str, name: str | None, path: str | None):
    """Add a data source to Dinobase.

    Supports 100+ sources: CRMs, billing, support, analytics, databases,
    e-commerce, dev tools, and more.

    Run `dinobase sources` to see all available sources.

    Examples:

      dinobase add stripe --api-key sk_test_...

      dinobase add hubspot --api-key pat-...

      dinobase add postgres --connection-string postgresql://user:pass@host/db

      dinobase add parquet --path ./data/events/

      dinobase add shopify --api-key shppa_... --shop-url myshop.myshopify.com
    """
    from dinobase.config import add_source as save_source, init_dinobase

    init_dinobase()

    # File sources — create views immediately, no sync needed
    if source_type in ("parquet", "csv"):
        if not path:
            path = click.prompt(f"Enter path to {source_type} files")
        source_name = name or path.rstrip("/").split("/")[-1].replace(".", "_")

        from dinobase.db import DinobaseDB
        from dinobase.sync.sources.parquet import add_file_source, extract_metadata

        db = DinobaseDB()
        result = add_file_source(db, source_name, path, file_format=source_type)

        annotations = extract_metadata(db, source_name)
        sync_id = db.log_sync_start(source_name, source_type)
        db.log_sync_end(
            sync_id, "success",
            tables_synced=len(result["tables"]),
            rows_synced=result["total_rows"],
        )
        db.update_table_metadata(source_name, source_name, annotations=annotations)
        save_source(source_name, source_type, {"path": path, "format": source_type})

        click.echo(f"\nAdded {len(result['tables'])} tables from {path} as '{source_name}'")
        click.echo(f"Total: {result['total_rows']:,} rows. Ready to query — no sync needed.")
        db.close()
        return

    # Registry-based sources
    from dinobase.sync.registry import get_source_entry, list_available_sources

    entry = get_source_entry(source_type)
    if entry is None:
        available = ", ".join(list_available_sources())
        click.echo(f"Unknown source: '{source_type}'", err=True)
        click.echo(f"Available sources: {available}", err=True)
        click.echo(f"Also: parquet, csv (file sources)", err=True)
        sys.exit(1)

    # Parse extra args as --flag value pairs
    extra_dict = _parse_extra_args(tuple(ctx.args))

    # Collect credentials — from CLI flags, env vars, or interactive prompts
    source_name = name or source_type
    credentials: dict[str, str] = {}

    for param in entry.credentials:
        # Check CLI flag (e.g., --api-key)
        flag_key = param.cli_flag.lstrip("-").replace("-", "_")
        value = extra_dict.get(flag_key)

        # Check env var
        if not value and param.env_var:
            import os
            value = os.environ.get(param.env_var)

        # Interactive prompt
        if not value:
            value = click.prompt(
                param.prompt or f"Enter {param.name}",
                hide_input=param.secret,
            )

        credentials[param.name] = value

    # Check for missing pip extras
    if entry.pip_extra:
        try:
            import importlib
            importlib.import_module(entry.pip_extra.replace("-", "_"))
        except ImportError:
            click.echo(f"Source '{source_type}' requires: pip install {entry.pip_extra}", err=True)
            sys.exit(1)

    sync_interval = extra_dict.get("sync_interval")
    save_source(source_name, source_type, credentials, sync_interval=sync_interval)
    click.echo(f"Added {source_type} source as '{source_name}'")
    if sync_interval:
        click.echo(f"Sync interval: {sync_interval}")
    click.echo(f"Run `dinobase sync` to load data.")


def _parse_extra_args(args: tuple) -> dict[str, str]:
    """Parse --flag value pairs from unprocessed args."""
    result = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i].lstrip("-").replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                result[key] = args[i + 1]
                i += 2
            else:
                result[key] = "true"
                i += 1
        else:
            i += 1
    return result


@cli.command("sources")
@click.option("--pretty", is_flag=True, help="Human-readable output with descriptions")
def list_sources_cmd(pretty: bool):
    """List all available source types."""
    from dinobase.sync.registry import SOURCES

    if not pretty:
        sources = sorted(SOURCES.keys()) + ["parquet", "csv"]
        click.echo(json.dumps(sources))
        return

    saas = []
    databases = []
    cloud_storage = []
    for name, entry in sorted(SOURCES.items()):
        extra = f"  (pip install {entry.pip_extra})" if entry.pip_extra else ""
        line = f"    {name:<20} {entry.description}{extra}"
        if "sql_database" in entry.import_path:
            databases.append(line)
        elif "filesystem" in entry.import_path:
            cloud_storage.append(line)
        else:
            saas.append(line)

    click.echo("Available sources:\n")

    click.echo("  SaaS APIs:")
    for line in saas:
        click.echo(line)

    click.echo("\n  Databases:")
    for line in databases:
        click.echo(line)

    click.echo("\n  Cloud storage (incremental sync):")
    for line in cloud_storage:
        click.echo(line)

    click.echo("\n  Files (no sync, instant):")
    click.echo(f"    {'parquet':<20} Parquet files (local, S3, GCS)")
    click.echo(f"    {'csv':<20} CSV files (local, S3, GCS)")


@cli.command()
@click.argument("source_name", required=False)
@click.option("--schedule", is_flag=True, help="Run as a daemon, syncing on configured intervals")
@click.option("--interval", default="1h", help="Default sync interval for --schedule (e.g. 30m, 1h, 6h)")
@click.option("--max-workers", default=10, help="Max concurrent syncs (default 10)")
def sync(source_name: str | None, schedule: bool, interval: str, max_workers: int):
    """Sync data from connected sources.

    By default, runs a one-time sync. Use --schedule to run continuously.
    Sources sync concurrently (up to --max-workers at a time).

    Examples:

      dinobase sync                    # sync all sources once
      dinobase sync salesforce         # sync one source
      dinobase sync --schedule         # run daemon, sync every 1h
      dinobase sync --schedule --interval 30m  # sync every 30m
      dinobase sync --max-workers 20   # sync up to 20 sources at once
    """
    from dinobase.config import get_sources, init_dinobase
    from dinobase.db import DinobaseDB

    init_dinobase()
    sources = get_sources()

    if not sources:
        click.echo("No sources configured. Run `dinobase add <source>` first.")
        sys.exit(1)

    # Scheduled mode — run as daemon
    if schedule:
        from dinobase.sync.scheduler import SyncScheduler

        db = DinobaseDB()
        scheduler = SyncScheduler(db, default_interval=interval, max_workers=max_workers)
        try:
            scheduler.run_loop()
        except KeyboardInterrupt:
            click.echo("\nScheduler stopped.")
        finally:
            db.close()
        return

    # One-time sync
    from dinobase.sync.engine import SyncEngine

    if source_name:
        if source_name not in sources:
            click.echo(f"Source '{source_name}' not found. Available: {', '.join(sources.keys())}")
            sys.exit(1)
        to_sync = {source_name: sources[source_name]}
    else:
        to_sync = sources

    db = DinobaseDB()
    engine = SyncEngine(db)

    total_tables = 0
    total_rows = 0

    for name, config in to_sync.items():
        # Skip file sources
        if config.get("type") in ("parquet", "csv"):
            continue
        result = engine.sync(name, config)
        if result.status == "success":
            click.echo(
                f"  {name}: synced {result.tables_synced} tables "
                f"({result.rows_synced:,} rows)"
            )
            total_tables += result.tables_synced
            total_rows += result.rows_synced
        else:
            click.echo(f"  {name}: ERROR — {result.error}", err=True)

    click.echo(f"\nDone. {total_tables} tables, {total_rows:,} rows total.")
    db.close()


@cli.command()
@click.option("--pretty", is_flag=True, help="Human-readable output instead of JSON")
def status(pretty: bool):
    """Show status of all sources."""
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    db = DinobaseDB()
    engine = QueryEngine(db)
    result = engine.list_sources()

    if not pretty:
        click.echo(json.dumps(result, indent=2, default=str))
        db.close()
        return

    if not result["sources"]:
        click.echo("No data loaded. Run `dinobase add <source>` then `dinobase sync`.")
        db.close()
        return

    for source in result["sources"]:
        click.echo(f"\n{source['name']}:")
        click.echo(f"  Tables: {source['table_count']}")
        click.echo(f"  Total rows: {source['total_rows']:,}")
        if source["last_sync"]:
            click.echo(f"  Last sync: {source['last_sync']}")
        for table in source["tables"]:
            click.echo(f"    {table['name']}: {table['rows']:,} rows")

    db.close()


@cli.command("query")
@click.argument("sql")
@click.option("--pretty", is_flag=True, help="Human-readable table output instead of JSON")
@click.option("--max-rows", default=200, help="Maximum rows to return")
def run_query(sql: str, pretty: bool, max_rows: int):
    """Execute a SQL query."""
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    db = DinobaseDB()
    engine = QueryEngine(db)
    result = engine.execute(sql, max_rows=max_rows)

    if "error" in result:
        click.echo(json.dumps(result, indent=2, default=str))
        db.close()
        sys.exit(1)

    if not pretty:
        click.echo(json.dumps(result, indent=2, default=str))
        db.close()
        return

    # Print as table
    if result["rows"]:
        columns = result["columns"]
        rows = result["rows"]

        # Calculate column widths
        widths = {col: len(col) for col in columns}
        for row in rows:
            for col in columns:
                val = str(row.get(col, ""))
                widths[col] = min(max(widths[col], len(val)), 40)

        # Header
        header = " | ".join(col.ljust(widths[col]) for col in columns)
        click.echo(header)
        click.echo("-+-".join("-" * widths[col] for col in columns))

        # Rows
        for row in rows:
            line = " | ".join(
                str(row.get(col, ""))[:40].ljust(widths[col]) for col in columns
            )
            click.echo(line)

    click.echo(f"\n{result['row_count']} rows", err=True)
    if result.get("truncated"):
        click.echo(result["message"], err=True)

    db.close()


@cli.command("describe")
@click.argument("table")
@click.option("--pretty", is_flag=True, help="Human-readable output instead of JSON")
def describe_table(table: str, pretty: bool):
    """Describe a table's columns, types, annotations, and sample data."""
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    db = DinobaseDB()
    engine = QueryEngine(db)
    result = engine.describe_table(table)

    if not pretty:
        click.echo(json.dumps(result, indent=2, default=str))
        db.close()
        if "error" in result:
            sys.exit(1)
        return

    if "error" in result:
        click.echo(f"Error: {result['error']}", err=True)
        db.close()
        sys.exit(1)

    click.echo(f"\n{result['schema']}.{result['table']} ({result['row_count']:,} rows)\n")

    for col in result["columns"]:
        line = f"  {col['name']:<25} {col['type']:<15}"
        if col.get("description"):
            line += f" — {col['description']}"
        click.echo(line)
        if col.get("note"):
            click.echo(f"  {'':25} {'':15}   {col['note']}")

    if result.get("sample_rows"):
        click.echo(f"\nSample data ({len(result['sample_rows'])} rows):")
        for row in result["sample_rows"]:
            click.echo(f"  {json.dumps(row, default=str)}")

    db.close()


@cli.command("confirm")
@click.argument("mutation_id")
def confirm_mutation(mutation_id: str):
    """Confirm and execute a pending mutation."""
    from dinobase.db import DinobaseDB
    from dinobase.query.mutations import MutationEngine

    db = DinobaseDB()
    engine = MutationEngine(db)
    result = engine.confirm(mutation_id)
    click.echo(json.dumps(result, indent=2, default=str))
    db.close()
    if "error" in result:
        sys.exit(1)


@cli.command("cancel")
@click.argument("mutation_id")
def cancel_mutation(mutation_id: str):
    """Cancel a pending mutation."""
    from dinobase.db import DinobaseDB
    from dinobase.query.mutations import MutationEngine

    db = DinobaseDB()
    engine = MutationEngine(db)
    result = engine.cancel(mutation_id)
    click.echo(json.dumps(result, indent=2, default=str))
    db.close()


@cli.command()
def info():
    """Show database overview for agents. Use this to understand what data is available."""
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine
    from dinobase.mcp.server import _build_instructions

    db = DinobaseDB()
    engine = QueryEngine(db)
    instructions = _build_instructions(engine)
    click.echo(instructions)
    db.close()


@cli.command(context_settings={"ignore_unknown_options": True})
@click.option("--sync", "sync_schedule", is_flag=True, help="Enable background sync scheduler")
@click.option("--sync-interval", default="1h", help="Default sync interval (e.g. 30m, 1h, 6h)")
def serve(sync_schedule: bool, sync_interval: str):
    """Start the Dinobase MCP server (stdio transport).

    Examples:

      dinobase serve                          # MCP server only
      dinobase serve --sync                   # MCP server + background sync every 1h
      dinobase serve --sync --sync-interval 30m  # sync every 30m
    """
    from dinobase.config import init_dinobase
    from dinobase.mcp.server import run_server

    init_dinobase()
    run_server(sync_schedule=sync_schedule, sync_interval=sync_interval)


@cli.command("mcp-config")
def mcp_config():
    """Print the MCP configuration for Claude Desktop."""
    import shutil

    # Find the dinobase executable
    dinobase_path = shutil.which("dinobase")
    if dinobase_path:
        config = {
            "mcpServers": {
                "dinobase": {
                    "command": dinobase_path,
                    "args": ["serve"],
                }
            }
        }
    else:
        config = {
            "mcpServers": {
                "dinobase": {
                    "command": sys.executable,
                    "args": ["-m", "dinobase.mcp.server"],
                }
            }
        }

    click.echo("Add this to your Claude Desktop config:")
    click.echo(f"(~/.claude/claude_desktop_config.json)\n")
    click.echo(json.dumps(config, indent=2))


if __name__ == "__main__":
    cli()
