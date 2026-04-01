"""CLI for Dinobase."""

from __future__ import annotations

import json
import sys

import click

from dinobase import __version__
from dinobase.annotations import AnnotateBatchInput, AnnotationInput, RelationshipInput, apply_annotation, apply_relationship


_AGENT_COMMANDS = frozenset({
    "info", "query", "describe", "status", "sources",
    "confirm", "cancel", "refresh", "auth",
})


def _get_cloud_client():
    """Return an authenticated CloudClient if logged in, else None."""
    import os
    from dinobase.config import load_cloud_credentials, get_cloud_api_url, ensure_fresh_cloud_token

    creds = load_cloud_credentials()
    if not creds:
        return None

    access_token = ensure_fresh_cloud_token()
    if not access_token:
        return None

    # DINOBASE_CLOUD_URL env var overrides stored api_url for local dev
    api_url = os.environ.get("DINOBASE_CLOUD_URL") or creds.get("api_url", get_cloud_api_url())

    from dinobase.cloud_client import CloudClient
    return CloudClient(
        api_url=api_url,
        access_token=access_token,
    )


class CategorizedGroup(click.Group):
    """Click group that shows commands in agent/admin categories."""

    def format_commands(self, ctx, formatter):
        agent_cmds = []
        admin_cmds = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            help_text = cmd.get_short_help_str(limit=150)
            if name in _AGENT_COMMANDS:
                agent_cmds.append((name, help_text))
            else:
                admin_cmds.append((name, help_text))

        if agent_cmds:
            with formatter.section("Agent commands"):
                formatter.write_dl(agent_cmds)
        if admin_cmds:
            with formatter.section("Admin commands (ignore if you're an agent)"):
                formatter.write_dl(admin_cmds)


@click.group(cls=CategorizedGroup)
@click.version_option(version=__version__)
def cli():
    """🦕 Dinobase — the agent-first database."""
    pass


def _require_init():
    """Check that Dinobase has been initialized. Exit with a friendly message if not."""
    from dinobase.config import get_dinobase_dir, get_db_path, is_cloud_storage

    # Cloud mode — config dir must exist but no local DB needed
    if is_cloud_storage():
        if not get_dinobase_dir().exists():
            click.echo("Dinobase is not initialized. Run `dinobase init` first.", err=True)
            sys.exit(1)
        return

    ddir = get_dinobase_dir()
    if not ddir.exists() or not get_db_path().exists():
        click.echo("Dinobase is not initialized. Run `dinobase init` first.", err=True)
        sys.exit(1)


@cli.command()
@click.option("--storage", help="Cloud storage URL (e.g., s3://bucket/dinobase/)")
def init(storage: str | None):
    """Initialize Dinobase (create config directory and database).

    Use --storage to store data in cloud storage instead of locally.

    Examples:

      dinobase init                                    # local mode
      dinobase init --storage s3://bucket/dinobase/    # S3 mode
      dinobase init --storage gs://bucket/dinobase/    # GCS mode
    """
    from dinobase.config import init_dinobase, get_db_path, is_cloud_storage

    ddir = init_dinobase(storage_url=storage)

    # Touch the database to create it
    from dinobase.db import DinobaseDB
    db = DinobaseDB()
    _ = db.conn  # triggers initialization
    db.close()

    click.echo(f"Dinobase initialized at {ddir}")
    if is_cloud_storage():
        from dinobase.config import get_storage_url
        click.echo(f"Storage: {get_storage_url()}")
    else:
        click.echo(f"Database: {get_db_path()}")
    click.echo("Add a source: dinobase add <source> --api-key ...  (run `dinobase sources` to list all)")


_QUICKSTART_SOURCES = [
    ("stripe",    "Stripe — payments, subscriptions, invoices"),
    ("hubspot",   "HubSpot — CRM, contacts, deals"),
    ("github",    "GitHub — repos, issues, pull requests"),
    ("postgres",  "PostgreSQL — any Postgres database"),
    ("shopify",   "Shopify — orders, products, customers"),
    ("zendesk",   "Zendesk — support tickets"),
    ("slack",     "Slack — channels, messages"),
    ("notion",    "Notion — databases and pages"),
]


@cli.command()
def quickstart():
    """Guided setup: connect sources and start querying in minutes.

    Walks you through picking a data source, entering credentials,
    and prints the MCP config snippet to connect with Claude or Cursor.

    Example:

      dinobase quickstart
    """
    import os
    from dinobase.config import init_dinobase, add_source as save_source, source_exists
    from dinobase.sync.registry import get_source_entry

    init_dinobase()

    click.echo("\nWelcome to Dinobase — the agent-first database.\n")
    click.echo("Connect your data sources and query them all with SQL.\n")

    added_sources: list[str] = []

    while True:
        click.echo("Pick a source to connect:\n")
        for i, (_, label) in enumerate(_QUICKSTART_SOURCES, 1):
            click.echo(f"  {i:2}. {label}")
        click.echo()
        click.echo("  Or type a source name (e.g. salesforce, jira, linear).")
        click.echo("  Run `dinobase sources --available` to see all 100+ sources.")
        if added_sources:
            click.echo("  Press Enter or type 'done' to finish.\n")
        else:
            click.echo()

        choice = click.prompt("Source", default="done" if added_sources else "").strip()

        if choice.lower() in ("done", "d", ""):
            break

        # Resolve source name from number or string
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(_QUICKSTART_SOURCES):
                source_type = _QUICKSTART_SOURCES[idx][0]
            else:
                click.echo(f"  Invalid number. Enter 1-{len(_QUICKSTART_SOURCES)} or a source name.\n")
                continue
        else:
            source_type = choice.lower()

        entry = get_source_entry(source_type)
        if entry is None:
            click.echo(f"  Unknown source '{source_type}'. Run `dinobase sources --available` to see all.\n")
            continue

        if source_exists(source_type):
            click.echo(f"  '{source_type}' is already connected.\n")
            if source_type not in added_sources:
                added_sources.append(source_type)
            continue

        # Show where to find credentials
        if entry.credential_help:
            click.echo(f"\n  Where to find credentials:\n    {entry.credential_help}\n")

        # Collect credentials
        credentials: dict[str, str] = {}
        aborted = False
        for param in entry.credentials:
            env_value = os.environ.get(param.env_var or "")
            if env_value:
                click.echo(f"  {param.name}: using ${param.env_var}")
                credentials[param.name] = env_value
                continue
            try:
                value = click.prompt(f"  {param.prompt or param.name}", hide_input=param.secret)
                credentials[param.name] = value
            except click.Abort:
                click.echo("\n  Cancelled.\n")
                aborted = True
                break

        if aborted:
            continue

        save_source(source_type, source_type, credentials)
        added_sources.append(source_type)
        click.echo(f"\n  Connected {source_type}.\n")

        if not click.confirm("  Add another source?", default=False):
            break
        click.echo()

    if not added_sources:
        click.echo("\nNo sources connected.")
        click.echo("Run `dinobase add <source>` to connect one, or `dinobase sources --available` to browse all.")
        return

    # Summary + next steps
    click.echo(f"\nConnected: {', '.join(added_sources)}\n")
    click.echo("Next steps:")
    click.echo(f"  dinobase sync                         # load data from your sources")
    click.echo(f"  dinobase info                         # see all synced tables")
    click.echo(f"  dinobase query 'SELECT ...'           # run SQL across sources")
    click.echo()

    # MCP config snippet
    import shutil
    dinobase_path = shutil.which("dinobase")
    server_entry = (
        {"command": dinobase_path, "args": ["serve"]}
        if dinobase_path
        else {"command": sys.executable, "args": ["-m", "dinobase.mcp.server"]}
    )
    click.echo("To use with Claude or Cursor, add this to your MCP config:\n")
    click.echo(json.dumps({"mcpServers": {"dinobase": server_entry}}, indent=2))
    click.echo()
    click.echo("Run `dinobase mcp-config` for per-client setup instructions.")


# ---------------------------------------------------------------------------
# Cloud account commands
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--headless", is_flag=True, help="Machine-readable output, no browser launch")
def login(headless: bool):
    """Sign in to Dinobase Cloud (free account).

    Opens your browser to create an account or sign in.
    After authentication, your CLI is configured for cloud mode.

    Examples:

      dinobase login              # opens browser
      dinobase login --headless   # prints login URL as JSON
    """
    import os
    from dinobase.config import (
        save_cloud_credentials, get_cloud_api_url, init_dinobase,
    )

    init_dinobase()
    api_url = get_cloud_api_url()
    web_url = os.environ.get("DINOBASE_WEB_URL", "http://localhost:3000")

    # Reuse the same local callback server pattern from auth.py
    from dinobase.auth import _start_callback_server
    import secrets
    import webbrowser
    from urllib.parse import urlencode, parse_qs, urlparse

    server = _start_callback_server()
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(32)

    # Open the web frontend's CLI login page — it handles auth and redirects back
    login_url = f"{web_url}/cli-login?" + urlencode({
        "callback": redirect_uri,
        "state": state,
    })

    if headless:
        click.echo(json.dumps({
            "status": "waiting",
            "login_url": login_url,
            "message": "Open this URL to sign in to Dinobase Cloud",
        }))
    else:
        click.echo("Opening browser to sign in to Dinobase Cloud...", err=True)
        click.echo(f"If the browser doesn't open, visit:\n  {login_url}\n", err=True)
        webbrowser.open(login_url)

    # Wait for callback
    server.timeout = 300
    while server.oauth_result is None:  # type: ignore[attr-defined]
        server.handle_request()

    server.server_close()
    result = server.oauth_result  # type: ignore[attr-defined]

    if "error" in result:
        click.echo(json.dumps({"status": "error", "error": result["error"]}))
        sys.exit(1)

    # The web frontend sends back the token directly via query params
    access_token = result.get("access_token")
    if not access_token:
        click.echo(json.dumps({"status": "error", "error": "No access token received"}))
        sys.exit(1)

    # Save credentials
    credentials = {
        "access_token": access_token,
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": int(result.get("expires_at", 0)),
        "user_id": result.get("user_id", ""),
        "email": result.get("email", ""),
        "api_url": api_url,
    }
    save_cloud_credentials(credentials)

    storage_url = result.get("storage_url")
    if storage_url:
        init_dinobase(storage_url=storage_url)

    email = result.get("email", "")
    if headless:
        click.echo(json.dumps({
            "status": "connected",
            "email": email,
            "storage_url": storage_url,
        }))
    else:
        click.echo(f"Logged in as {email}")
        if storage_url:
            click.echo(f"Storage: {storage_url}")
        click.echo("Run `dinobase auth <source>` to connect data sources via OAuth.")


@cli.command()
def logout():
    """Sign out of Dinobase Cloud."""
    from dinobase.config import clear_cloud_credentials, is_cloud_logged_in

    if not is_cloud_logged_in():
        click.echo("Not logged in.")
        return

    clear_cloud_credentials()
    click.echo("Logged out of Dinobase Cloud.")


@cli.command()
def whoami():
    """Show current Dinobase Cloud account info."""
    cloud = _get_cloud_client()
    if not cloud:
        click.echo(json.dumps({"logged_in": False}))
        return

    try:
        user_info = cloud.whoami()
        click.echo(json.dumps(user_info, indent=2, default=str))
    except RuntimeError as e:
        click.echo(json.dumps({"logged_in": False, "error": str(e)}))


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
    from dinobase.config import add_source as save_source, init_dinobase, source_exists

    init_dinobase()

    # Cloud mode — register source with the API
    cloud = _get_cloud_client()
    if cloud and source_type not in ("parquet", "csv"):
        from dinobase.sync.registry import get_source_entry, list_available_sources

        entry = get_source_entry(source_type)
        if entry is None:
            available = ", ".join(list_available_sources())
            click.echo(f"Unknown source: '{source_type}'", err=True)
            click.echo(f"Available sources: {available}", err=True)
            sys.exit(1)

        extra_dict = _parse_extra_args(tuple(ctx.args))
        source_name = name or source_type
        credentials: dict[str, str] = {}

        for param in entry.credentials:
            flag_key = param.cli_flag.lstrip("-").replace("-", "_")
            value = extra_dict.get(flag_key)
            if not value and param.env_var:
                import os
                value = os.environ.get(param.env_var)
            if not value:
                value = click.prompt(param.prompt or f"Enter {param.name}", hide_input=param.secret)
            credentials[param.name] = value

        try:
            result = cloud.add_source(source_name, source_type, credentials)
            click.echo(f"Added {source_type} source as '{source_name}' (cloud)")
            click.echo(f"Run `dinobase sync` to load data.")
        except RuntimeError as e:
            click.echo(f"Failed: {e}", err=True)
            sys.exit(1)
        return

    # File sources — create views immediately, no sync needed
    if source_type in ("parquet", "csv"):
        if not path:
            path = click.prompt(f"Enter path to {source_type} files")
        source_name = name or path.rstrip("/").split("/")[-1].replace(".", "_")
        if source_exists(source_name):
            if not click.confirm(f"Source '{source_name}' already exists. Overwrite?"):
                click.echo("Aborted.")
                return

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
    if source_exists(source_name):
        if not click.confirm(f"Source '{source_name}' already exists. Overwrite?"):
            click.echo("Aborted.")
            return
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
    freshness_threshold = extra_dict.get("freshness")
    save_source(
        source_name, source_type, credentials,
        sync_interval=sync_interval,
        freshness_threshold=freshness_threshold,
    )
    click.echo(f"Added {source_type} source as '{source_name}'")
    if sync_interval:
        click.echo(f"Sync interval: {sync_interval}")
    if freshness_threshold:
        click.echo(f"Freshness threshold: {freshness_threshold}")
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


@cli.command()
@click.argument("source_type")
@click.option("--name", help="Custom name for the source (defaults to source type)")
@click.option("--headless", is_flag=True, help="Machine-readable output, no browser launch")
def auth(source_type: str, name: str | None, headless: bool):
    """Connect a source via OAuth (requires Dinobase Cloud account).

    Opens your browser to authorize Dinobase to access the source.
    Tokens are stored in the cloud and refreshed automatically.

    Examples:

      dinobase auth hubspot

      dinobase auth salesforce --name my_salesforce

      dinobase auth hubspot --headless   # for agents
    """
    from dinobase.config import is_cloud_logged_in
    from dinobase.sync.registry import get_source_entry, list_available_sources

    # Validate source type first
    entry = get_source_entry(source_type)
    if entry is None:
        available = ", ".join(list_available_sources())
        click.echo(f"Unknown source: '{source_type}'", err=True)
        click.echo(f"Available sources: {available}", err=True)
        sys.exit(1)

    # Require cloud login for OAuth
    if not is_cloud_logged_in():
        if headless:
            click.echo(json.dumps({
                "status": "error",
                "error": "Cloud account required for OAuth",
                "message": "Run `dinobase login` first (free), or use `dinobase add <source> --api-key` for manual setup.",
            }))
        else:
            click.echo(
                "Dinobase Cloud account required for OAuth sources.\n"
                "Run `dinobase login` to sign up (free), or use "
                "`dinobase add <source> --api-key ...` for manual API key setup.",
                err=True,
            )
        sys.exit(1)

    cloud = _get_cloud_client()
    source_name = name or source_type

    # Start OAuth flow via the cloud API using local callback server
    from dinobase.auth import _start_callback_server
    import secrets
    import webbrowser
    from urllib.parse import urlencode

    server = _start_callback_server()
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"

    try:
        oauth_info = cloud.start_oauth(source_name, redirect_uri)
    except RuntimeError as e:
        click.echo(json.dumps({"status": "error", "error": str(e)}) if headless else f"OAuth failed: {e}")
        sys.exit(1)

    auth_url = oauth_info["auth_url"]
    state = oauth_info.get("state", "")

    if headless:
        click.echo(json.dumps({
            "status": "waiting",
            "auth_url": auth_url,
            "message": f"Open this URL to connect {source_type}",
        }))
    else:
        click.echo(f"Opening browser to authorize {source_type}...", err=True)
        click.echo(f"If the browser doesn't open, visit:\n  {auth_url}\n", err=True)
        webbrowser.open(auth_url)

    # Wait for callback
    server.timeout = 300
    while server.oauth_result is None:  # type: ignore[attr-defined]
        server.handle_request()

    server.server_close()
    result = server.oauth_result  # type: ignore[attr-defined]

    if "error" in result:
        msg = f"OAuth failed: {result['error']}"
        click.echo(json.dumps({"status": "error", "error": msg}) if headless else msg)
        sys.exit(1)

    code = result.get("code")
    if not code:
        click.echo(json.dumps({"status": "error", "error": "No auth code received"}) if headless else "No auth code received")
        sys.exit(1)

    # Complete OAuth via cloud API
    try:
        completion = cloud.complete_oauth(source_name, code, redirect_uri, state)
    except RuntimeError as e:
        click.echo(json.dumps({"status": "error", "error": str(e)}) if headless else f"OAuth completion failed: {e}")
        sys.exit(1)

    if headless:
        click.echo(json.dumps({
            "status": "connected",
            "source": source_name,
            "type": source_type,
        }))
    else:
        click.echo(f"Connected {source_type} as '{source_name}' via OAuth.")
        click.echo(f"Run `dinobase sync` to load data.")


@cli.command("sources")
@click.option("--available", is_flag=True, help="Show all available source types (not just connected)")
@click.option("--pretty", is_flag=True, help="Human-readable output with descriptions")
def list_sources_cmd(available: bool, pretty: bool):
    """List connected data sources, or all available source types with --available."""
    if available:
        _list_available_sources(pretty)
        return

    # Cloud mode — list sources from the API
    cloud = _get_cloud_client()
    if cloud:
        try:
            sources = cloud.list_sources()
            if not pretty:
                click.echo(json.dumps(sources, indent=2, default=str))
            elif not sources:
                click.echo("No sources connected. Run `dinobase auth <source>` to connect one.")
            else:
                for src in sources:
                    click.echo(f"  {src['name']:<20} type={src['type']}  ({src['auth_method']})")
                click.echo(f"\n{len(sources)} source(s) connected.")
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        return

    # Local mode — show connected sources from config
    from dinobase.config import get_sources

    sources = get_sources()
    if not sources:
        if pretty:
            click.echo("No sources connected. Run `dinobase add <source>` to add one.")
            click.echo("Run `dinobase sources --available` to see all available source types.")
        else:
            click.echo(json.dumps([]))
        return

    if not pretty:
        click.echo(json.dumps(list(sources.keys())))
        return

    for name, config in sources.items():
        source_type = config.get("type", name)
        click.echo(f"  {name:<20} type={source_type}")

    click.echo(f"\n{len(sources)} source(s) connected.")
    click.echo("Run `dinobase sources --available` to see all available source types.")


def _list_available_sources(pretty: bool):
    """Show all available source types from the registry."""
    from dinobase.sync.registry import SOURCES

    if not pretty:
        sources = []
        for _name, entry in sorted(SOURCES.items()):
            sources.append(entry.to_dict())
        # Add file sources
        sources.append({
            "name": "parquet",
            "description": "Parquet files (local, S3, GCS)",
            "supports_oauth": False,
            "credential_help": None,
            "credentials": [{"name": "path", "cli_flag": "--path", "env_var": None, "prompt": "Path to parquet files", "secret": False}],
            "pip_extra": None,
        })
        sources.append({
            "name": "csv",
            "description": "CSV files (local, S3, GCS)",
            "supports_oauth": False,
            "credential_help": None,
            "credentials": [{"name": "path", "cli_flag": "--path", "env_var": None, "prompt": "Path to CSV files", "secret": False}],
            "pip_extra": None,
        })
        click.echo(json.dumps(sources, indent=2))
        return

    saas = []
    databases = []
    cloud_storage = []
    for name, entry in sorted(SOURCES.items()):
        extra = f"  (pip install {entry.pip_extra})" if entry.pip_extra else ""
        oauth_tag = " [oauth]" if entry.supports_oauth else ""
        line = f"    {name:<20} {entry.description}{oauth_tag}{extra}"
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
    # Cloud mode — trigger server-side sync
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.trigger_sync(source_name)
            click.echo(json.dumps(result, indent=2, default=str))
        except RuntimeError as e:
            click.echo(f"Sync failed: {e}", err=True)
            sys.exit(1)
        return

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
        # Skip file sources with a clear message
        if config.get("type") in ("parquet", "csv"):
            click.echo(f"  {name}: file source — no sync needed (query directly)")
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
@click.argument("source_name", required=False)
@click.option("--stale", is_flag=True, help="Refresh only stale sources")
@click.option("--pretty", is_flag=True, help="Human-readable output instead of JSON")
def refresh(source_name: str | None, stale: bool, pretty: bool):
    """Re-sync sources to get fresh data. Blocks until complete (typically 10-60s per source).

    Without arguments, refreshes all sources. Use --stale to refresh
    only sources that exceed their freshness threshold.

    Examples:

      dinobase refresh                 # refresh all sources
      dinobase refresh stripe          # refresh one source
      dinobase refresh --stale         # refresh only stale sources
      dinobase refresh --stale --pretty  # human-readable output
    """
    # Cloud mode — trigger sync via API
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.trigger_sync(source_name)
            if not pretty:
                click.echo(json.dumps(result, indent=2, default=str))
            else:
                click.echo(f"Sync triggered for {result.get('sources', '?')} source(s).")
        except RuntimeError as e:
            click.echo(f"Refresh failed: {e}", err=True)
            sys.exit(1)
        return

    from dinobase.config import get_sources, init_dinobase
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine
    from dinobase.sync.engine import SyncEngine

    init_dinobase()
    sources = get_sources()

    if not sources:
        click.echo("No sources configured. Run `dinobase add <source>` first.")
        sys.exit(1)

    db = DinobaseDB()
    engine = QueryEngine(db)
    sync_engine = SyncEngine(db)

    # Determine which sources to refresh
    if source_name:
        if source_name not in sources:
            click.echo(f"Source '{source_name}' not found. Available: {', '.join(sources.keys())}")
            db.close()
            sys.exit(1)
        to_refresh = {source_name: sources[source_name]}
    elif stale:
        to_refresh = {}
        for name, config in sources.items():
            if config.get("type") in ("parquet", "csv"):
                continue
            freshness = engine.get_freshness(name)
            if freshness["is_stale"]:
                to_refresh[name] = config
        if not to_refresh:
            if pretty:
                click.echo("All sources are fresh.")
            else:
                click.echo(json.dumps({"status": "all_fresh"}))
            db.close()
            return
    else:
        # No args, no --stale: refresh all non-file sources
        to_refresh = {
            name: config for name, config in sources.items()
            if config.get("type") not in ("parquet", "csv")
        }
        if not to_refresh:
            click.echo("No syncable sources to refresh.")
            db.close()
            return

    results = []
    for name, config in to_refresh.items():
        if config.get("type") in ("parquet", "csv"):
            continue

        if pretty:
            freshness_before = engine.get_freshness(name)
            click.echo(f"Refreshing {name} (was {freshness_before.get('age_human', '?')} old)...")

        result = sync_engine.sync(name, config)
        freshness_after = engine.get_freshness(name)

        if pretty:
            if result.status == "success":
                click.echo(
                    f"  {name}: synced {result.tables_synced} tables "
                    f"({result.rows_synced:,} rows) — now fresh"
                )
            else:
                click.echo(f"  {name}: ERROR — {result.error}", err=True)
        else:
            results.append({
                "source": name,
                "status": result.status,
                "tables_synced": result.tables_synced,
                "rows_synced": result.rows_synced,
                "error": result.error,
                "freshness": freshness_after,
            })

    if not pretty:
        click.echo(json.dumps(results, indent=2, default=str))

    db.close()


@cli.command()
@click.option("--pretty", is_flag=True, help="Human-readable output instead of JSON")
def status(pretty: bool):
    """Show status of all sources."""
    # Cloud mode
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.sync_status()
            if not pretty:
                click.echo(json.dumps(result, indent=2, default=str))
            else:
                for src in result:
                    status_tag = f" [{src['status']}]" if src.get("status") else ""
                    click.echo(f"\n{src['source']}:{status_tag}")
                    click.echo(f"  Type: {src.get('type', '?')}")
                    click.echo(f"  Tables: {src.get('tables_synced', 0)}")
                    click.echo(f"  Rows: {src.get('rows_synced', 0):,}")
                    if src.get("last_sync"):
                        click.echo(f"  Last sync: {src['last_sync']}")
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        return

    _require_init()
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    db = DinobaseDB()
    engine = QueryEngine(db)
    result = engine.list_sources()

    if not pretty:
        click.echo(json.dumps(result, indent=2, default=str))
        db.close()
        return

    # Show storage location
    from dinobase.config import is_cloud_storage, get_storage_url
    if is_cloud_storage():
        click.echo(f"Storage: {get_storage_url()}")
    else:
        from dinobase.config import get_db_path
        click.echo(f"Storage: {get_db_path()} (local)")

    if not result["sources"]:
        click.echo("\nNo data loaded. Run `dinobase add <source>` then `dinobase sync`.")
        db.close()
        return

    for source in result["sources"]:
        status_tag = ""
        if source.get("is_stale"):
            status_tag = " [STALE]"
        elif source.get("age"):
            status_tag = " [fresh]"

        click.echo(f"\n{source['name']}:{status_tag}")
        click.echo(f"  Tables: {source['table_count']}")
        click.echo(f"  Total rows: {source['total_rows']:,}")
        if source["last_sync"]:
            age_str = f" ({source['age']} ago)" if source.get("age") else ""
            click.echo(f"  Last sync: {source['last_sync']}{age_str}")
        if source.get("freshness_threshold"):
            click.echo(f"  Freshness threshold: {source['freshness_threshold']}")
        for table in source["tables"]:
            click.echo(f"    {table['name']}: {table['rows']:,} rows")

    db.close()


@cli.command("query")
@click.argument("sql")
@click.option("--pretty", is_flag=True, help="Human-readable table output instead of JSON")
@click.option("--max-rows", default=200, help="Maximum rows to return")
def run_query(sql: str, pretty: bool, max_rows: int):
    """Execute a SQL query."""
    # Cloud mode
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.query(sql, max_rows=max_rows)
        except RuntimeError as e:
            click.echo(json.dumps({"error": str(e)}, indent=2))
            sys.exit(1)
        # Fall through to the same display logic below
        if "error" in result:
            click.echo(json.dumps(result, indent=2, default=str))
            sys.exit(1)
        if not pretty:
            click.echo(json.dumps(result, indent=2, default=str))
            return
        # Pretty-print (reuse same table rendering below)
        if result.get("rows"):
            columns = result["columns"]
            rows = result["rows"]
            widths = {col: len(col) for col in columns}
            for row in rows:
                for col in columns:
                    val = str(row.get(col, ""))
                    widths[col] = min(max(widths[col], len(val)), 40)
            header = " | ".join(col.ljust(widths[col]) for col in columns)
            click.echo(header)
            click.echo("-+-".join("-" * widths[col] for col in columns))
            for row in rows:
                line = " | ".join(str(row.get(col, ""))[:40].ljust(widths[col]) for col in columns)
                click.echo(line)
        click.echo(f"\n{result.get('row_count', 0)} rows", err=True)
        return

    _require_init()
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
    # Cloud mode
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.describe(table)
        except RuntimeError as e:
            click.echo(json.dumps({"error": str(e)}, indent=2))
            sys.exit(1)
        if not pretty:
            click.echo(json.dumps(result, indent=2, default=str))
            if "error" in result:
                sys.exit(1)
            return
        if "error" in result:
            click.echo(f"Error: {result['error']}", err=True)
            sys.exit(1)
        click.echo(f"\n{result.get('schema','')}.{result.get('table','')} ({result.get('row_count',0):,} rows)\n")
        for col in result.get("columns", []):
            line = f"  {col['name']:<25} {col['type']:<15}"
            if col.get("description"):
                line += f" -- {col['description']}"
            click.echo(line)
        return

    _require_init()
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
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.confirm(mutation_id)
            click.echo(json.dumps(result, indent=2, default=str))
        except RuntimeError as e:
            click.echo(json.dumps({"error": str(e)}, indent=2))
            sys.exit(1)
        return

    _require_init()
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
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.cancel(mutation_id)
            click.echo(json.dumps(result, indent=2, default=str))
        except RuntimeError as e:
            click.echo(json.dumps({"error": str(e)}, indent=2))
            sys.exit(1)
        return

    _require_init()
    from dinobase.db import DinobaseDB
    from dinobase.query.mutations import MutationEngine

    db = DinobaseDB()
    engine = MutationEngine(db)
    result = engine.cancel(mutation_id)
    click.echo(json.dumps(result, indent=2, default=str))
    db.close()
    if "error" in result:
        sys.exit(1)



@cli.command("annotate", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1)
@click.option("--cardinality", default="one_to_many", type=click.Choice(["one_to_one", "one_to_many", "many_to_many"]), help="Relationship cardinality (4-arg mode)")
@click.option("--description", default="", help="Relationship description (4-arg mode)")
@click.option("--input-schema", is_flag=True, help="Print JSON input schema and exit")
def annotate(args: tuple, cardinality: str, description: str, input_schema: bool):
    """Annotate tables, columns, or relationships.

    Human usage:

      dinobase annotate github.issues description "All GitHub issues"
      dinobase annotate github.issues.body pii true
      dinobase annotate stripe.subscriptions customer_id stripe.customers id
      dinobase annotate stripe.subscriptions customer_id stripe.customers id --cardinality one_to_many

    Agent usage (JSON):

      dinobase annotate '{"target": "github.issues", "key": "description", "value": "..."}'
      dinobase annotate '{"from_table": "stripe.subscriptions", "from_column": "customer_id", "to_table": "stripe.customers", "to_column": "id"}'
      dinobase annotate '[{"target": "..."}, {"from_table": "...", ...}]'
      dinobase annotate --input-schema
    """
    if input_schema:
        click.echo(json.dumps(AnnotateBatchInput.model_json_schema(), indent=2))
        return

    # JSON mode: single arg that parses as JSON object or array
    if len(args) == 1:
        try:
            data = json.loads(args[0])
        except (json.JSONDecodeError, ValueError):
            data = None
        if data is not None:
            raw_items = data if isinstance(data, list) else [data]
            _require_init()
            from dinobase.db import DinobaseDB
            db = DinobaseDB()
            results = []
            for raw in raw_items:
                if "target" in raw:
                    item = AnnotationInput.model_validate(raw)
                    results.append(apply_annotation(db, item))
                elif "from_table" in raw:
                    item = RelationshipInput.model_validate(raw)
                    results.append(apply_relationship(db, item))
                else:
                    results.append({"error": f"Cannot determine item type: {raw}"})
            db.close()
            click.echo(json.dumps(results if len(results) > 1 else results[0], indent=2))
            if any("error" in r for r in results):
                sys.exit(1)
            return

    # Human positional mode
    _require_init()
    from dinobase.db import DinobaseDB
    db = DinobaseDB()

    if len(args) == 3:
        target, key, value = args
        result = apply_annotation(db, AnnotationInput(target=target, key=key, value=value))
    elif len(args) == 4:
        from_table, from_column, to_table, to_column = args
        for t in (from_table, to_table):
            if len(t.split(".")) != 2:
                click.echo(json.dumps({"error": f"Invalid table '{t}'. Use 'schema.table'"}))
                db.close()
                sys.exit(1)
        result = apply_relationship(db, RelationshipInput(
            from_table=from_table, from_column=from_column,
            to_table=to_table, to_column=to_column,
            cardinality=cardinality, description=description,
        ))
    else:
        click.echo("Usage: annotate TARGET KEY VALUE  or  annotate FROM_TABLE FROM_COL TO_TABLE TO_COL")
        db.close()
        sys.exit(1)

    db.close()
    click.echo(json.dumps(result))
    if "error" in result:
        sys.exit(1)


@cli.command()
def info():
    """Show database overview for agents. Use this to understand what data is available."""
    # Cloud mode
    cloud = _get_cloud_client()
    if cloud:
        try:
            result = cloud.info()
            click.echo(result.get("instructions", ""))
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        return

    _require_init()
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine
    from dinobase.mcp.server import _build_instructions

    db = DinobaseDB()
    engine = QueryEngine(db)
    instructions = _build_instructions(engine)
    click.echo(instructions)
    db.close()


@cli.command()
def doctor():
    """Check your Dinobase setup and diagnose common problems.

    Verifies that the config directory, database, credentials, and storage
    are all set up correctly.

    Example:

      dinobase doctor
    """
    import stat
    from dinobase.config import (
        get_dinobase_dir, get_config_path, get_db_path,
        load_config, is_cloud_storage, get_storage_url,
    )

    ok = True

    def _pass(msg: str) -> None:
        click.echo(f"  [ok]   {msg}")

    def _fail(msg: str, hint: str = "") -> None:
        nonlocal ok
        ok = False
        click.echo(f"  [fail] {msg}", err=True)
        if hint:
            click.echo(f"         {hint}", err=True)

    def _warn(msg: str) -> None:
        click.echo(f"  [warn] {msg}")

    click.echo("Checking Dinobase setup...\n")

    # 1. Config directory
    ddir = get_dinobase_dir()
    if ddir.exists():
        _pass(f"Config directory exists: {ddir}")
    else:
        _fail(f"Config directory not found: {ddir}", "Run `dinobase init` to create it.")

    # 2. Config file
    config_path = get_config_path()
    if config_path.exists():
        _pass(f"Config file exists: {config_path}")
        # Check file permissions
        mode = config_path.stat().st_mode
        world_readable = bool(mode & stat.S_IROTH)
        if world_readable:
            _warn(f"Config file is world-readable (contains API keys). Run: chmod 600 {config_path}")
        else:
            _pass("Config file permissions are restricted (owner-only)")
        # Try parsing
        try:
            config = load_config()
            _pass(f"Config file is valid YAML")
        except SystemExit:
            _fail("Config file has a YAML parse error", f"Fix manually: {config_path}")
    else:
        _fail(f"Config file not found", "Run `dinobase init` to create it.")

    # 3. Database / storage
    if is_cloud_storage():
        storage_url = get_storage_url()
        _pass(f"Cloud storage configured: {storage_url}")
    else:
        db_path = get_db_path()
        if isinstance(db_path, str):
            _pass("In-memory mode (no local database file)")
        elif db_path.exists():
            _pass(f"Local database exists: {db_path}")
        else:
            _fail(f"Local database not found: {db_path}", "Run `dinobase init` to create it.")

    # 4. Connected sources
    try:
        config = load_config()
        sources = config.get("sources", {})
        if sources:
            _pass(f"{len(sources)} source(s) configured: {', '.join(sources.keys())}")
        else:
            _warn("No sources configured. Run `dinobase add <source>` or `dinobase quickstart`.")
    except Exception:
        pass  # Already reported above

    # 5. Cloud account
    from dinobase.config import is_cloud_logged_in
    if is_cloud_logged_in():
        _pass("Logged in to Dinobase Cloud")
    else:
        _warn("Not logged in to Dinobase Cloud (optional). Run `dinobase login` for OAuth sources.")

    # 6. dinobase binary
    import shutil
    dinobase_bin = shutil.which("dinobase")
    if dinobase_bin:
        _pass(f"dinobase binary found: {dinobase_bin}")
    else:
        _warn("dinobase binary not in PATH. Use `python -m dinobase.cli` instead.")

    click.echo()
    if ok:
        click.echo("All checks passed. Run `dinobase sync` to load data.")
    else:
        click.echo("Some checks failed. Fix the issues above and run `dinobase doctor` again.")
        sys.exit(1)


@cli.command("config")
def open_config():
    """Open the config file in your default editor.

    Example:

      dinobase config
    """
    from dinobase.config import get_config_path, init_dinobase

    init_dinobase()
    path = get_config_path()
    click.echo(f"Opening {path}")
    click.launch(str(path))


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
@click.argument("client", required=False, default=None,
                type=click.Choice(["claude-desktop", "claude-code", "cursor"], case_sensitive=False))
def mcp_config(client: str | None):
    """Print MCP configuration for Claude Desktop, Claude Code, or Cursor.

    Without arguments, prints configs for all three clients.

    Examples:

      dinobase mcp-config                # show all configs
      dinobase mcp-config claude-desktop # Claude Desktop only
      dinobase mcp-config claude-code    # Claude Code only
      dinobase mcp-config cursor         # Cursor only
    """
    import shutil

    # Build the server entry
    dinobase_path = shutil.which("dinobase")
    if dinobase_path:
        server_entry = {
            "command": dinobase_path,
            "args": ["serve"],
        }
    else:
        server_entry = {
            "command": sys.executable,
            "args": ["-m", "dinobase.mcp.server"],
        }

    mcp_block = {"mcpServers": {"dinobase": server_entry}}

    clients = {
        "claude-desktop": {
            "label": "Claude Desktop",
            "path": "~/.claude/claude_desktop_config.json",
        },
        "claude-code": {
            "label": "Claude Code",
            "path": ".mcp.json (in your project root)",
        },
        "cursor": {
            "label": "Cursor",
            "path": ".cursor/mcp.json (in your project root)",
        },
    }

    targets = [client] if client else list(clients.keys())

    for i, name in enumerate(targets):
        info = clients[name]
        if i > 0:
            click.echo()
        click.echo(f"# {info['label']}")
        click.echo(f"# Add to {info['path']}\n")
        click.echo(json.dumps(mcp_block, indent=2))


@cli.command("install")
@click.argument("client", type=click.Choice(
    ["claude-code", "claude-desktop", "cursor"], case_sensitive=False
))
def install_mcp(client: str):
    """Install the Dinobase MCP server into your AI client.

    Examples:

      dinobase install claude-code      # runs: claude mcp add dinobase -- dinobase serve
      dinobase install claude-desktop   # writes mcpServers entry to Claude Desktop config
      dinobase install cursor           # writes mcpServers entry to .cursor/mcp.json
    """
    import shutil
    import subprocess
    from pathlib import Path

    # Build server entry (same logic as mcp-config)
    dinobase_path = shutil.which("dinobase")
    server_entry = (
        {"command": dinobase_path, "args": ["serve"]}
        if dinobase_path
        else {"command": sys.executable, "args": ["-m", "dinobase.mcp.server"]}
    )

    if client == "claude-code":
        try:
            subprocess.run(
                ["claude", "mcp", "add", "dinobase", "--", "dinobase", "serve"],
                check=True,
            )
        except FileNotFoundError:
            raise click.ClickException("'claude' CLI not found — install it from https://claude.ai/code")
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"claude mcp add failed: {e}")
        return

    if client == "claude-desktop":
        if sys.platform == "darwin":
            config_path = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
        elif sys.platform == "win32":
            config_path = Path(os.environ["APPDATA"]) / "Claude/claude_desktop_config.json"
        else:
            config_path = Path.home() / ".config/Claude/claude_desktop_config.json"
    else:  # cursor
        config_path = Path.cwd() / ".cursor/mcp.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(config_path.read_text()) if config_path.exists() else {}
    data.setdefault("mcpServers", {})["dinobase"] = server_entry
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    click.echo(f"✓ Dinobase MCP added to {config_path}")


if __name__ == "__main__":
    cli()
