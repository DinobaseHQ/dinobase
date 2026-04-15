"""CLI for Dinobase."""

from __future__ import annotations

import json
import sys

import click

from dinobase import __version__
from dinobase.annotations import AnnotateBatchInput, AnnotationInput, RelationshipInput, apply_annotation, apply_relationship


_AGENT_COMMANDS = frozenset({
    "info", "query", "describe", "status", "connectors",
    "confirm", "cancel", "refresh", "auth", "mcp",
})

_CLI_INSTRUCTIONS = """\
Dinobase is installed on this system. It gives you SQL access to the user's business data
(Stripe, HubSpot, Postgres, and 100+ other sources) synced into a local DuckDB database.

Use the CLI — it is more token-efficient than MCP.

Workflow:
1. `dinobase info` — see what sources and tables are available
2. `dinobase describe <schema.table>` — columns, types, annotations, relationships, sample data
3. `dinobase query "<sql>"` — run SQL (DuckDB dialect, reference tables as schema.table)
4. `dinobase refresh [source]` — re-sync stale data before querying
5. `dinobase annotate '<json>'` — document tables/columns: descriptions, PII flags, relationships

For mutations (INSERT/UPDATE/DELETE), `query` returns a preview with a mutation ID.
Call `dinobase confirm <id>` to execute or `dinobase cancel <id>` to discard.

MCP tool proxy — call tools on connected MCP servers directly:
- `dinobase mcp servers` — list connected MCP servers and their tools
- `dinobase mcp instructions <server>` — show a server's usage instructions
- `dinobase mcp info <server>[.tool]` — list tools or show one tool's schema (parameters, types)
- `dinobase mcp search "<pattern>"` — regex search tool names/descriptions across all servers
- `dinobase mcp call <server.tool> ['{"arg": "value"}']` — call a tool with optional JSON args

Prefer the SQL interface (`dinobase query`) over MCP retrieval tools for reading data.
MCP server data is automatically synced into DuckDB tables (schema: server name, table: tool name).
SQL lets you filter, join, aggregate, and paginate — much more powerful than raw tool calls.
Use `mcp call` only for actions (writes, mutations) or tools that need specific arguments.
Note: only tools with no required parameters are auto-synced into tables.

When writing code that calls MCP tools, prefer the Python API over shelling out to the CLI:
  from dinobase.mcp import call, tools, servers, search, instructions
  call("server.tool", arg=value)  — call a tool with keyword args
  tools("server")                 — list tools with schemas
  servers()                       — list connected MCP servers
  search("pattern")               — regex search across all servers
  instructions("server")          — server info and usage instructions

Always start with `dinobase info` to understand what data is available.
Output is JSON by default. Add --pretty for human-readable tables."""


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

    def invoke(self, ctx):
        from dinobase import telemetry
        cmd = ctx.protected_args[0] if ctx.protected_args else (ctx.args[0] if ctx.args else "unknown")
        telemetry.capture("cli_invoked", {"command": cmd})

        # Auto-update before running the command (skips agent commands)
        if cmd not in _AGENT_COMMANDS:
            try:
                from dinobase.updater import maybe_auto_update
                maybe_auto_update(cmd)
            except Exception:
                pass

        return super().invoke(ctx)

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

    # Prompt for agent setup (interactive) or print instructions (non-interactive)
    if sys.stdin.isatty():
        click.echo("\nSet up an agent? (optional)\n")
        choices = [
            ("1", "claude-code",    "Claude Code"),
            ("2", "cursor",         "Cursor"),
            ("3", "claude-desktop", "Claude Desktop"),
            ("4", "codex",          "Codex"),
        ]
        for num, _, label in choices:
            click.echo(f"  {num}. {label}")
        click.echo("  5. Skip\n")
        choice = click.prompt("Choose", default="5", show_default=False)
        matched = {num: client for num, client, _ in choices}
        if choice in matched:
            _install_client(matched[choice])
        elif choice != "5":
            click.echo("Skipped.")
    else:
        click.echo("\nSet up your coding agent:\n")
        click.echo("  dinobase install claude-code       # Claude Code")
        click.echo("  dinobase install cursor            # Cursor")
        click.echo("  dinobase install claude-desktop    # Claude Desktop")
        click.echo("  dinobase install codex             # Codex")
        click.echo("\nDocs: https://dinobase.ai/docs")


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
    click.echo("  dinobase sync                         # load data from your sources")
    click.echo("  dinobase info                         # see all synced tables")
    click.echo("  dinobase query 'SELECT ...'           # run SQL across sources")
    click.echo()

    # MCP config snippet
    import shutil
    dinobase_path = shutil.which("dinobase")
    server_entry = (
        {"command": dinobase_path, "args": ["serve"]}
        if dinobase_path
        else {"command": sys.executable, "args": ["-m", "dinobase.mcp"]}
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
    web_url = os.environ.get("DINOBASE_WEB_URL", "https://app.dinobase.ai")

    # Reuse the same local callback server pattern from auth.py
    from dinobase.auth import _start_callback_server
    import secrets
    import webbrowser
    from urllib.parse import urlencode

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

    if result.get("state") != state:
        click.echo(json.dumps({"status": "error", "error": "State mismatch — possible CSRF. Try logging in again."}))
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

    from dinobase import telemetry
    telemetry.identify(credentials["user_id"], credentials["email"])
    telemetry.capture("login_completed", {"email": credentials["email"]})

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
    from dinobase import telemetry
    telemetry.capture("logout")
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
            from dinobase import telemetry
            telemetry.capture("source_added", {"source_type": source_type, "auth_method": "api_key", "is_cloud_mode": True, "surface": "cli"})
            click.echo(f"Added {source_type} source as '{source_name}' (cloud)")
            click.echo("Run `dinobase sync` to load data.")
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
        from dinobase import telemetry
        telemetry.capture("source_added", {"source_type": source_type, "auth_method": "file", "is_cloud_mode": False, "surface": "cli"})

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
        click.echo("Also: parquet, csv (file sources)", err=True)
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
    from dinobase import telemetry
    telemetry.capture("source_added", {"source_type": source_type, "auth_method": "api_key", "is_cloud_mode": False, "surface": "cli"})
    click.echo(f"Added {source_type} source as '{source_name}'")
    if sync_interval:
        click.echo(f"Sync interval: {sync_interval}")
    if freshness_threshold:
        click.echo(f"Freshness threshold: {freshness_threshold}")
    click.echo("Run `dinobase sync` to load data.")


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
    import webbrowser

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
        click.echo("Run `dinobase sync` to load data.")


@cli.command("connectors")
@click.option("--available", is_flag=True, help="Show all available connector types (not just connected)")
@click.option("--pretty", is_flag=True, help="Human-readable output with descriptions")
def list_connectors_cmd(available: bool, pretty: bool):
    """List connected data connectors, or all available connector types with --available."""
    if available:
        _list_available_connectors(pretty)
        return

    # Cloud mode — list connectors from the API
    cloud = _get_cloud_client()
    if cloud:
        try:
            connectors = cloud.list_connectors()
            if not pretty:
                click.echo(json.dumps(connectors, indent=2, default=str))
            elif not connectors:
                click.echo("No connectors connected. Run `dinobase auth <connector>` to connect one.")
            else:
                for src in connectors:
                    click.echo(f"  {src['name']:<20} type={src['type']}  ({src['auth_method']})")
                click.echo(f"\n{len(connectors)} connector(s) connected.")
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        return

    # Local mode — show connected connectors from config
    from dinobase.config import get_connectors

    connectors = get_connectors()
    if not connectors:
        if pretty:
            click.echo("No connectors configured. Run `dinobase add <connector>` to add one.")
            click.echo("Run `dinobase connectors --available` to see all available connector types.")
        else:
            click.echo(json.dumps([]))
        return

    if not pretty:
        click.echo(json.dumps(list(connectors.keys())))
        return

    for name, config in connectors.items():
        connector_type = config.get("type", name)
        click.echo(f"  {name:<20} type={connector_type}")

    click.echo(f"\n{len(connectors)} connector(s) connected.")
    click.echo("Run `dinobase connectors --available` to see all available connector types.")


@cli.command("sources", hidden=True)
@click.option("--available", is_flag=True)
@click.option("--pretty", is_flag=True)
@click.pass_context
def list_sources_cmd(ctx: click.Context, available: bool, pretty: bool):
    """Deprecated: use `dinobase connectors` instead."""
    click.echo("Note: `dinobase sources` is deprecated, use `dinobase connectors`.", err=True)
    ctx.invoke(list_connectors_cmd, available=available, pretty=pretty)


def _list_available_connectors(pretty: bool):
    """Show all available connector types from the registry."""
    from dinobase.sync.registry import SOURCES

    if not pretty:
        connectors = []
        for _name, entry in sorted(SOURCES.items()):
            connectors.append(entry.to_dict())
        # Add file connectors
        connectors.append({
            "name": "parquet",
            "description": "Parquet files (local, S3, GCS)",
            "supports_oauth": False,
            "credential_help": None,
            "credentials": [{"name": "path", "cli_flag": "--path", "env_var": None, "prompt": "Path to parquet files", "secret": False}],
            "pip_extra": None,
        })
        connectors.append({
            "name": "csv",
            "description": "CSV files (local, S3, GCS)",
            "supports_oauth": False,
            "credential_help": None,
            "credentials": [{"name": "path", "cli_flag": "--path", "env_var": None, "prompt": "Path to CSV files", "secret": False}],
            "pip_extra": None,
        })
        click.echo(json.dumps(connectors, indent=2))
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

    click.echo("Available connectors:\n")

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
    """Sync data from connected connectors.

    By default, runs a one-time sync. Use --schedule to run continuously.
    Connectors sync concurrently (up to --max-workers at a time).

    Examples:

      dinobase sync                    # sync all connectors once
      dinobase sync salesforce         # sync one connector
      dinobase sync --schedule         # run daemon, sync every 1h
      dinobase sync --schedule --interval 30m  # sync every 30m
      dinobase sync --max-workers 20   # sync up to 20 connectors at once
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

    from dinobase.config import get_connectors, init_dinobase
    from dinobase.db import DinobaseDB

    init_dinobase()
    connectors = get_connectors()

    if not connectors:
        click.echo("No connectors configured. Run `dinobase add <connector>` first.")
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

    from dinobase.fetch.connector import is_local_connector

    if source_name:
        if source_name not in connectors:
            # Check if it's a standalone local connector (e.g. MCP)
            if is_local_connector(source_name):
                connectors[source_name] = {"type": source_name}
            else:
                click.echo(f"Connector '{source_name}' not found. Available: {', '.join(connectors.keys())}")
                sys.exit(1)
        to_sync = {source_name: connectors[source_name]}
    else:
        to_sync = connectors

    db = DinobaseDB()
    engine = SyncEngine(db)

    total_tables = 0
    total_rows = 0

    for name, config in to_sync.items():
        # Skip file connectors with a clear message
        if config.get("type") in ("parquet", "csv"):
            click.echo(f"  {name}: file connector — no sync needed (query directly)")
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
    """Re-sync connectors to get fresh data. Blocks until complete (typically 10-60s per connector).

    Without arguments, refreshes all connectors. Use --stale to refresh
    only connectors that exceed their freshness threshold.

    Examples:

      dinobase refresh                 # refresh all connectors
      dinobase refresh stripe          # refresh one connector
      dinobase refresh --stale         # refresh only stale connectors
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
                click.echo(f"Sync triggered for {result.get('connectors', '?')} connector(s).")
        except RuntimeError as e:
            click.echo(f"Refresh failed: {e}", err=True)
            sys.exit(1)
        return

    from dinobase.config import get_connectors, init_dinobase
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine
    from dinobase.sync.engine import SyncEngine

    init_dinobase()
    connectors = get_connectors()

    if not connectors:
        click.echo("No connectors configured. Run `dinobase add <connector>` first.")
        sys.exit(1)

    db = DinobaseDB()
    engine = QueryEngine(db)
    sync_engine = SyncEngine(db)

    from dinobase.fetch.connector import is_local_connector

    # Determine which connectors to refresh
    if source_name:
        if source_name not in connectors:
            if is_local_connector(source_name):
                connectors[source_name] = {"type": source_name}
            else:
                click.echo(f"Connector '{source_name}' not found. Available: {', '.join(connectors.keys())}")
                db.close()
                sys.exit(1)
        to_refresh = {source_name: connectors[source_name]}
    elif stale:
        to_refresh = {}
        for name, config in connectors.items():
            if config.get("type") in ("parquet", "csv"):
                continue
            freshness = engine.get_freshness(name)
            if freshness["is_stale"]:
                to_refresh[name] = config
        if not to_refresh:
            if pretty:
                click.echo("All connectors are fresh.")
            else:
                click.echo(json.dumps({"status": "all_fresh"}))
            db.close()
            return
    else:
        # No args, no --stale: refresh all non-file connectors
        to_refresh = {
            name: config for name, config in connectors.items()
            if config.get("type") not in ("parquet", "csv")
        }
        if not to_refresh:
            click.echo("No syncable connectors to refresh.")
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
    result = engine.list_connectors()

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

    if not result["connectors"]:
        click.echo("\nNo data loaded. Run `dinobase add <connector>` then `dinobase sync`.")
        db.close()
        return

    for connector in result["connectors"]:
        status_tag = ""
        if connector.get("is_stale"):
            status_tag = " [STALE]"
        elif connector.get("age"):
            status_tag = " [fresh]"

        click.echo(f"\n{connector['name']}:{status_tag}")
        click.echo(f"  Tables: {connector['table_count']}")
        click.echo(f"  Total rows: {connector['total_rows']:,}")
        if connector["last_sync"]:
            age_str = f" ({connector['age']} ago)" if connector.get("age") else ""
            click.echo(f"  Last sync: {connector['last_sync']}{age_str}")
        if connector.get("freshness_threshold"):
            click.echo(f"  Freshness threshold: {connector['freshness_threshold']}")
        for table in connector["tables"]:
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
            _pass("Config file is valid YAML")
        except SystemExit:
            _fail("Config file has a YAML parse error", f"Fix manually: {config_path}")
    else:
        _fail("Config file not found", "Run `dinobase init` to create it.")

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

    # 4. Connected connectors
    try:
        config = load_config()
        connectors = config.get("connectors", {})
        if connectors:
            _pass(f"{len(connectors)} connector(s) configured: {', '.join(connectors.keys())}")
        else:
            _warn("No connectors configured. Run `dinobase add <connector>` or `dinobase quickstart`.")
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
            "args": ["-m", "dinobase.mcp"],
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


def _upsert_tagged_block(path, tag: str, content: str) -> None:
    """Insert or replace a <tag>...</tag> block in a markdown file."""
    import re

    path.parent.mkdir(parents=True, exist_ok=True)
    tagged = f"<{tag}>\n{content}\n</{tag}>"
    if path.exists():
        text = path.read_text()
        pattern = re.compile(rf"<{re.escape(tag)}>.*?</{re.escape(tag)}>", re.DOTALL)
        if pattern.search(text):
            text = pattern.sub(tagged, text)
        else:
            text = text.rstrip() + "\n\n" + tagged + "\n"
    else:
        text = tagged + "\n"
    path.write_text(text)


_AGENT_CLIENTS = ["claude-code", "claude-desktop", "cursor", "codex"]


def _install_client(client: str) -> None:
    """Install Dinobase config for a given AI client."""
    import shutil
    from pathlib import Path

    from dinobase import telemetry

    if client == "claude-code":
        target = Path.home() / ".claude" / "CLAUDE.md"
        _upsert_tagged_block(target, "dinobase", _CLI_INSTRUCTIONS)
        click.echo(f"✓ Dinobase instructions added to {target}")

    elif client == "codex":
        target = Path.home() / ".codex" / "AGENTS.md"
        _upsert_tagged_block(target, "dinobase", _CLI_INSTRUCTIONS)
        click.echo(f"✓ Dinobase instructions added to {target}")

    elif client == "cursor":
        target = Path.cwd() / "AGENTS.md"
        _upsert_tagged_block(target, "dinobase", _CLI_INSTRUCTIONS)
        click.echo(f"✓ Dinobase instructions added to {target} (local)")

    elif client == "claude-desktop":
        import os
        # Desktop can't run CLI — install MCP server config
        dinobase_path = shutil.which("dinobase")
        server_entry = (
            {"command": dinobase_path, "args": ["serve"]}
            if dinobase_path
            else {"command": sys.executable, "args": ["-m", "dinobase.mcp"]}
        )
        if sys.platform == "darwin":
            config_path = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
        elif sys.platform == "win32":
            config_path = Path(os.environ["APPDATA"]) / "Claude/claude_desktop_config.json"
        else:
            config_path = Path.home() / ".config/Claude/claude_desktop_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(config_path.read_text()) if config_path.exists() else {}
        data.setdefault("mcpServers", {})["dinobase"] = server_entry
        config_path.write_text(json.dumps(data, indent=2) + "\n")
        click.echo(f"✓ Dinobase MCP added to {config_path}")

    if telemetry.was_installed(client):
        telemetry.capture("client_reinstalled", {"client": client})
    else:
        telemetry.capture("client_installed", {"client": client})
        telemetry.mark_installed(client)


@cli.command("install")
@click.argument("client", type=click.Choice(_AGENT_CLIENTS, case_sensitive=False))
def install_cmd(client: str):
    """Install Dinobase into your AI coding tool.

    For claude-code, cursor, and codex: writes CLI usage instructions
    to the tool's instructions file.

    For claude-desktop: writes MCP server config (Desktop can't run CLI).

    Examples:

      dinobase install claude-code      # writes to ~/.claude/CLAUDE.md
      dinobase install codex            # writes to ~/.codex/AGENTS.md
      dinobase install cursor           # writes to ./AGENTS.md (local)
      dinobase install claude-desktop   # writes MCP config to Claude Desktop
    """
    _install_client(client)


@cli.command()
@click.option("--check", is_flag=True, help="Only check for updates, don't install.")
def update(check: bool):
    """Check for and install Dinobase updates.

    Examples:

      dinobase update           # update to latest version
      dinobase update --check   # just check, don't install
    """
    from dinobase.updater import check_for_update, perform_update, detect_install_method, get_update_command

    click.echo(f"Current version: {__version__}")

    update_info = check_for_update(force=True)

    if not update_info or not update_info.get("update_available"):
        click.echo("Already up to date.")
        return

    latest = update_info["latest_version"]
    method = detect_install_method()

    if check:
        click.echo(f"Update available: {latest}")
        click.echo(f"Run `dinobase update` to install, or: {get_update_command(method)}")
        return

    click.echo(f"Updating to {latest} via {method}...")
    success, message = perform_update()

    if success:
        click.echo(message)
        # cli_updated is captured inside updater.perform_update().
    else:
        click.echo(message, err=True)
        click.echo(f"\nManual update: {get_update_command(method)}")
        sys.exit(1)


# ===================================================================
# Connector management (local custom connectors)
# ===================================================================


@cli.group()
def connector():
    """Manage local custom connectors."""
    pass


@connector.command("create")
@click.argument("name")
@click.option("--url", help="Base URL for the API (e.g., https://api.example.com/)")
@click.option(
    "--auth-type",
    type=click.Choice(["bearer", "http_basic", "api_key_header"]),
    default="bearer",
    help="Authentication type (default: bearer)",
)
@click.option("--endpoint", help="Endpoint path (e.g., projects/123/feature_flags/)")
@click.option("--data-selector", default="$", help="JSON path to data array (default: $ for root)")
@click.option("--mode", type=click.Choice(["live", "sync", "auto"]), default="auto", help="Fetch mode")
@click.option("--transport", type=click.Choice(["stdio", "sse", "streamable_http"]), help="MCP transport type")
@click.option("--command", help="MCP stdio command (e.g., 'npx -y @modelcontextprotocol/server-filesystem /data')")
def connector_create(
    name: str,
    url: str | None,
    auth_type: str,
    endpoint: str | None,
    data_selector: str,
    mode: str,
    transport: str | None,
    command: str | None,
):
    """Create a new local connector YAML config.

    Examples:

      dinobase connector create posthog_flags \\
        --url "https://app.posthog.com/api/" \\
        --endpoint "projects/123/feature_flags/" \\
        --data-selector results

      dinobase connector create my_api

      dinobase connector create my_files \\
        --transport stdio \\
        --command "npx -y @modelcontextprotocol/server-filesystem /data"

      dinobase connector create remote_tools \\
        --transport sse --url http://localhost:8080/sse
    """
    from dinobase.config import get_connectors_dir
    from dinobase.connectors.templates import (
        build_mcp_connector_yaml,
        build_rest_connector_yaml,
    )

    connectors_dir = get_connectors_dir()
    connectors_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = connectors_dir / f"{name}.yaml"
    if yaml_path.exists():
        click.echo(f"Error: connector '{name}' already exists at {yaml_path}", err=True)
        sys.exit(1)

    # MCP connector path
    if transport:
        try:
            content = build_mcp_connector_yaml(
                name=name,
                transport=transport,
                command=command,
                url=url,
                mode=mode,
            )
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        yaml_path.write_text(content)
        click.echo(f"Created MCP connector: {yaml_path}")
        from dinobase import telemetry
        telemetry.capture("custom_connector_created", {
            "kind": "mcp",
            "transport": transport,
            "surface": "cli",
        })
        click.echo(f"\nNext steps:")
        click.echo(f"  1. Sync: dinobase sync {name}")
        click.echo(f"  2. Query: dinobase query \"SELECT * FROM {name}.<tool_name> LIMIT 10\"")
        return

    # REST connector path
    resource_name = (endpoint or name).strip("/").split("/")[-1] or name
    content = build_rest_connector_yaml(
        name=name,
        url=url,
        auth_type=auth_type,
        endpoint=endpoint,
        data_selector=data_selector,
        mode=mode,
    )

    yaml_path.write_text(content)
    click.echo(f"Created connector: {yaml_path}")
    from dinobase import telemetry
    telemetry.capture("custom_connector_created", {
        "kind": "rest",
        "auth_type": auth_type,
        "surface": "cli",
    })
    click.echo(f"\nNext steps:")
    click.echo(f"  1. Edit the config: dinobase connector edit {name}")
    click.echo(f"  2. Add credentials: dinobase add {name} --api-key YOUR_KEY")
    click.echo(f"  3. Query: dinobase query \"SELECT * FROM {name}.{resource_name} LIMIT 10\"")


@connector.command("list")
@click.option("--pretty", is_flag=True, help="Human-readable output")
def connector_list(pretty: bool):
    """List all local custom connectors."""
    from dinobase.config import get_connectors_dir

    import yaml

    connectors_dir = get_connectors_dir()
    if not connectors_dir.is_dir():
        if pretty:
            click.echo("No local connectors directory found.")
        else:
            click.echo(json.dumps([]))
        return

    connectors = []
    for path in sorted(connectors_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            from dinobase.fetch.connector import get_connector_mode

            connectors.append({
                "name": cfg.get("name", path.stem),
                "description": cfg.get("description", ""),
                "mode": get_connector_mode(cfg),
                "resources": [r["name"] for r in cfg.get("resources", [])],
                "path": str(path),
            })
        except Exception as e:
            connectors.append({
                "name": path.stem,
                "error": str(e),
                "path": str(path),
            })

    if pretty:
        if not connectors:
            click.echo("No local connectors. Create one with: dinobase connector create <name>")
            return
        for c in connectors:
            if "error" in c:
                click.echo(f"  {c['name']} — ERROR: {c['error']}")
            else:
                resources = ", ".join(c["resources"]) if c["resources"] else "(none)"
                click.echo(f"  {c['name']} ({c['mode']}) — {c['description']}")
                click.echo(f"    resources: {resources}")
    else:
        click.echo(json.dumps(connectors, indent=2))


@connector.command("edit")
@click.argument("name")
def connector_edit(name: str):
    """Open a local connector config in your editor."""
    import os

    from dinobase.config import get_connectors_dir

    yaml_path = get_connectors_dir() / f"{name}.yaml"
    if not yaml_path.exists():
        click.echo(f"Error: connector '{name}' not found at {yaml_path}", err=True)
        click.echo(f"Create it with: dinobase connector create {name}")
        sys.exit(1)

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL"))
    if editor:
        os.execlp(editor, editor, str(yaml_path))
    else:
        click.echo(f"No $EDITOR set. Config path: {yaml_path}")


@connector.command("validate")
@click.argument("name")
def connector_validate(name: str):
    """Validate a local connector YAML config."""
    from dinobase.config import get_connectors_dir

    import yaml

    yaml_path = get_connectors_dir() / f"{name}.yaml"
    if not yaml_path.exists():
        click.echo(f"Error: connector '{name}' not found at {yaml_path}", err=True)
        sys.exit(1)

    try:
        with open(yaml_path) as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as e:
        click.echo(f"YAML parse error: {e}", err=True)
        sys.exit(1)

    errors = []

    if not cfg.get("name"):
        errors.append("Missing required field: name")
    if not cfg.get("client", {}).get("base_url"):
        errors.append("Missing required field: client.base_url")
    if not cfg.get("resources"):
        errors.append("No resources defined — add at least one resource")

    for i, r in enumerate(cfg.get("resources", [])):
        if not r.get("name"):
            errors.append(f"Resource #{i + 1}: missing 'name' field")
        if not r.get("endpoint", {}).get("path"):
            errors.append(f"Resource '{r.get('name', f'#{i + 1}')}': missing endpoint.path")

    # Check credential placeholders
    import re

    base_url = cfg.get("client", {}).get("base_url", "")
    auth_token = cfg.get("client", {}).get("auth", {}).get("token", "")
    placeholders = set(re.findall(r"\{(\w+)\}", base_url + auth_token))
    cred_names = {c["name"] for c in cfg.get("credentials", [])}
    for resource in cfg.get("resources", []):
        path = resource.get("endpoint", {}).get("path", "")
        placeholders.update(re.findall(r"\{(\w+)\}", path))

    undefined = placeholders - cred_names
    if undefined:
        errors.append(
            f"Undefined credential placeholders: {', '.join(sorted(undefined))}. "
            f"Add them to the 'credentials' list."
        )

    if errors:
        click.echo(f"Validation failed for {name}:", err=True)
        for e in errors:
            click.echo(f"  - {e}", err=True)
        sys.exit(1)
    else:
        click.echo(f"Connector '{name}' is valid.")


# ---------------------------------------------------------------------------
# MCP tool proxy commands
# ---------------------------------------------------------------------------


def _get_mcp_connectors() -> list[dict[str, Any]]:
    """Scan connectors dir for MCP connectors (those with transport: key)."""
    from dinobase.config import get_connectors_dir

    import yaml

    connectors_dir = get_connectors_dir()
    if not connectors_dir.is_dir():
        return []

    results = []
    for path in sorted(connectors_dir.glob("*.yaml")):
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            if cfg and "transport" in cfg:
                results.append(cfg)
        except Exception:
            continue
    return results


@cli.group()
def mcp():
    """Proxy MCP server tools — list, search, inspect, and call."""
    pass


@mcp.command("servers")
@click.option("--pretty", is_flag=True, help="Human-readable output")
def mcp_servers(pretty: bool):
    """List connected MCP servers and their tools."""
    import asyncio

    from dinobase.fetch.mcp_connector import list_all_tools

    connectors = _get_mcp_connectors()
    if not connectors:
        if pretty:
            click.echo("No MCP servers configured. Create one with:")
            click.echo("  dinobase connector create <name> --transport stdio --command '...'")
        else:
            click.echo(json.dumps({"servers": []}))
        return

    servers = []
    for cfg in connectors:
        name = cfg["name"]
        transport = cfg["transport"]
        entry: dict[str, Any] = {
            "name": name,
            "description": cfg.get("description", ""),
            "transport": transport["type"],
        }
        if transport["type"] == "stdio":
            entry["command"] = transport.get("command", "")
        else:
            entry["url"] = transport.get("url", "")

        try:
            tools = asyncio.run(list_all_tools(name))
            entry["tools"] = len(tools)
            entry["tool_names"] = [t["name"] for t in tools]
        except Exception as e:
            entry["tools"] = 0
            entry["error"] = str(e)

        servers.append(entry)

    if pretty:
        for s in servers:
            status = f"{s['tools']} tools" if "error" not in s else f"error: {s['error']}"
            click.echo(f"  {s['name']} ({s['transport']}) — {status}")
            if s.get("tool_names"):
                for t in s["tool_names"]:
                    click.echo(f"    - {t}")
    else:
        click.echo(json.dumps({"servers": servers}, indent=2, default=str))


@mcp.command("instructions")
@click.argument("server")
@click.option("--pretty", is_flag=True, help="Human-readable output")
def mcp_instructions(server: str, pretty: bool):
    """Show an MCP server's instructions (how to use it).

    Examples:

      dinobase mcp instructions my_server
    """
    import asyncio

    from dinobase.fetch.mcp_connector import get_server_info

    try:
        info = asyncio.run(get_server_info(server))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        sys.exit(1)

    if pretty:
        if info.get("name"):
            version = f" v{info['version']}" if info.get("version") else ""
            click.echo(f"{info['name']}{version}\n")
        if info.get("instructions"):
            click.echo(info["instructions"])
        else:
            click.echo("(no instructions provided by this server)")
    else:
        click.echo(json.dumps(info, indent=2, default=str))


@mcp.command("info")
@click.argument("ref")
@click.option("--pretty", is_flag=True, help="Human-readable output")
def mcp_info(ref: str, pretty: bool):
    """Show tool schema. REF is 'server' (list all) or 'server.tool' (one tool).

    Examples:

      dinobase mcp info my_server
      dinobase mcp info my_server.list_files
    """
    import asyncio

    from dinobase.fetch.mcp_connector import list_all_tools

    if "." in ref:
        server, tool_name = ref.split(".", 1)
    else:
        server, tool_name = ref, None

    try:
        tools = asyncio.run(list_all_tools(server))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        sys.exit(1)

    if tool_name:
        match = [t for t in tools if t["name"] == tool_name]
        if not match:
            available = [t["name"] for t in tools]
            click.echo(
                json.dumps({"error": f"Tool '{tool_name}' not found on '{server}'", "available": available}),
            )
            sys.exit(1)
        result = match[0]

        if pretty:
            click.echo(f"{server}.{result['name']}")
            if result.get("description"):
                click.echo(f"  {result['description']}")
            schema = result.get("inputSchema", {})
            props = schema.get("properties", {})
            required = set(schema.get("required", []))
            if props:
                click.echo(f"\n  Parameters:")
                for pname, pdef in props.items():
                    req = " (required)" if pname in required else ""
                    ptype = pdef.get("type", "any")
                    desc = pdef.get("description", "")
                    click.echo(f"    {pname}: {ptype}{req}")
                    if desc:
                        click.echo(f"      {desc}")
            ann = result.get("annotations", {})
            if ann:
                flags = []
                if ann.get("readOnlyHint"):
                    flags.append("read-only")
                if ann.get("destructiveHint"):
                    flags.append("destructive")
                if ann.get("idempotentHint"):
                    flags.append("idempotent")
                if flags:
                    click.echo(f"\n  Annotations: {', '.join(flags)}")
        else:
            click.echo(json.dumps(result, indent=2, default=str))
    else:
        # List all tools on the server
        if pretty:
            click.echo(f"{server} — {len(tools)} tools\n")
            for t in tools:
                desc = f" — {t['description']}" if t.get("description") else ""
                params = t.get("inputSchema", {}).get("properties", {})
                required = t.get("inputSchema", {}).get("required", [])
                param_str = ""
                if params:
                    parts = []
                    for p in params:
                        parts.append(f"{p}*" if p in required else p)
                    param_str = f" ({', '.join(parts)})"
                click.echo(f"  {t['name']}{param_str}{desc}")
        else:
            click.echo(json.dumps({"server": server, "tools": tools}, indent=2, default=str))


@mcp.command("search")
@click.argument("pattern")
@click.option("--pretty", is_flag=True, help="Human-readable output")
def mcp_search(pattern: str, pretty: bool):
    """Search tools across all MCP servers by regex.

    Matches against tool names and descriptions.

    Examples:

      dinobase mcp search "list.*"
      dinobase mcp search "file"
    """
    import asyncio
    import re as _re

    from dinobase.fetch.mcp_connector import list_all_tools

    connectors = _get_mcp_connectors()
    if not connectors:
        click.echo(json.dumps({"matches": []}))
        return

    try:
        regex = _re.compile(pattern, _re.IGNORECASE)
    except _re.error as e:
        click.echo(json.dumps({"error": f"Invalid regex: {e}"}))
        sys.exit(1)

    matches = []
    for cfg in connectors:
        name = cfg["name"]
        try:
            tools = asyncio.run(list_all_tools(name))
        except Exception:
            continue

        for t in tools:
            text = t["name"] + " " + (t.get("description") or "")
            if regex.search(text):
                matches.append({
                    "server": name,
                    "tool": t["name"],
                    "description": t.get("description", ""),
                })

    if pretty:
        if not matches:
            click.echo(f"No tools matching '{pattern}'")
        else:
            click.echo(f"{len(matches)} match(es):\n")
            for m in matches:
                desc = f" — {m['description']}" if m["description"] else ""
                click.echo(f"  {m['server']}.{m['tool']}{desc}")
    else:
        click.echo(json.dumps({"matches": matches}, indent=2, default=str))


@mcp.command("call")
@click.argument("ref")
@click.argument("args_json", required=False, default=None)
@click.option("--pretty", is_flag=True, help="Human-readable output")
def mcp_call(ref: str, args_json: str | None, pretty: bool):
    """Call an MCP tool. REF is 'server.tool', ARGS_JSON is optional JSON arguments.

    Examples:

      dinobase mcp call my_server.list_allowed_directories
      dinobase mcp call my_server.list_directory '{"path": "/tmp"}'
    """
    import asyncio

    from dinobase.fetch.mcp_connector import call_tool

    if "." not in ref:
        click.echo(json.dumps({"error": "Use server.tool format (e.g. my_server.list_files)"}))
        sys.exit(1)

    server, tool_name = ref.split(".", 1)

    arguments = {}
    if args_json:
        try:
            arguments = json.loads(args_json)
        except json.JSONDecodeError as e:
            click.echo(json.dumps({"error": f"Invalid JSON arguments: {e}"}))
            sys.exit(1)

    try:
        result = asyncio.run(call_tool(server, tool_name, arguments))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        sys.exit(1)

    if pretty:
        if result.get("isError"):
            click.echo("Error:", err=True)
        has_text = False
        for block in result.get("content", []):
            if block.get("type") == "text":
                click.echo(block["text"])
                has_text = True
        if not has_text and result.get("structuredContent"):
            click.echo(json.dumps(result["structuredContent"], indent=2, default=str))
    else:
        click.echo(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    cli()
