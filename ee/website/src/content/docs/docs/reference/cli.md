---
title: CLI Reference
description: Complete reference for all Dinobase CLI commands, options, and flags.
---

Run `dinobase --help` for a summary, or `dinobase <command> --help` for any command.

## `dinobase init`

Create the config directory and database.

```bash
dinobase init [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--storage` | Cloud storage URL (e.g., `s3://bucket/dinobase/`, `gs://bucket/dinobase/`, `az://container/dinobase/`) |

Creates `~/.dinobase/` with `config.yaml` and `dinobase.duckdb`. Safe to run multiple times.

With `--storage`, data is stored in cloud storage instead of locally. See the [Cloud Storage Backend](/docs/guides/cloud-storage-backend/) guide.

```bash
dinobase init                                    # local (default)
dinobase init --storage s3://bucket/dinobase/    # S3
dinobase init --storage gs://bucket/dinobase/    # GCS
dinobase init --storage az://container/dinobase/ # Azure
```

---

## `dinobase setup`

Launch a local browser GUI for adding connectors (SaaS APIs, databases,
files, MCP servers, and custom REST). See the [Setup GUI guide](/docs/guides/setup-ui/) for details.

```bash
dinobase setup [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--port` | Bind a specific port (default: random) |
| `--no-browser` | Print the URL but don't open a browser |

Binds to `127.0.0.1` only, opens a browser tab, and blocks until you press
Ctrl+C or click **Quit setup** in the GUI.

---

## `dinobase add <type>`

Add a connector.

```bash
dinobase add <connector_type> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--name` | Custom name for the connector (defaults to type) |
| `--path` | Path to files (parquet/csv connectors only) |
| `--sync-interval` | Sync interval (e.g., `30m`, `1h`, `6h`) |
| `--freshness` | Freshness threshold (e.g., `1h`, `30m`). Defaults: 1h for SaaS, 6h for databases |

Connector-specific flags (e.g., `--api-key`, `--connection-string`) are passed through.

```bash
dinobase add stripe --api-key sk_live_...
dinobase add stripe --api-key sk_live_... --freshness 30m
dinobase add parquet --path ./data/ --name analytics
dinobase add postgres --connection-string postgresql://... --name prod --sync-interval 30m
```

---

## `dinobase connectors`

List configured connectors, or all available connector types. The deprecated alias `dinobase sources` still works and prints a deprecation notice.

```bash
dinobase connectors [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--available` | Show all available connector types (not just configured) |
| `--pretty` | Human-readable output |

By default shows only your configured connectors. Use `--available` to see all 100+ supported connector types grouped by category.

---

## `dinobase sync [connector]`

Sync data from configured connectors.

```bash
dinobase sync [CONNECTOR_NAME] [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--schedule` | off | Run as daemon |
| `--interval` | `1h` | Default interval for `--schedule` |
| `--max-workers` | `10` | Max concurrent syncs |

```bash
dinobase sync                              # all connectors, once
dinobase sync stripe                       # one connector
dinobase sync --schedule --interval 30m    # daemon mode
```

---

## `dinobase refresh [connector]`

Re-sync connectors to get fresh data.

```bash
dinobase refresh [CONNECTOR_NAME] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--stale` | Refresh only connectors that exceed their freshness threshold |
| `--pretty` | Human-readable output |

```bash
dinobase refresh                 # refresh all connectors
dinobase refresh stripe          # refresh one connector
dinobase refresh --stale         # refresh only stale connectors
dinobase refresh --stale --pretty
```

Without arguments, refreshes all non-file connectors. Use `--stale` to only refresh connectors past their freshness threshold.

---

## `dinobase status`

Show status of all connectors.

```bash
dinobase status [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--pretty` | Human-readable output |

---

## `dinobase query "<sql>"`

Execute a SQL query (DuckDB dialect).

```bash
dinobase query "<sql>" [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--pretty` | off | Table output |
| `--max-rows` | `200` | Max rows returned |

```bash
dinobase query "SELECT * FROM stripe.customers LIMIT 5" --pretty
dinobase query "SELECT COUNT(*) FROM hubspot.contacts"
```

---

## `dinobase describe <table>`

Describe a table's columns, types, annotations, and sample data.

```bash
dinobase describe <table> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--pretty` | Human-readable output |

`table` can be `schema.table` or just `table` (searches all schemas).

---

## `dinobase info`

Show database overview for agents. Outputs the same text used as MCP server instructions.

```bash
dinobase info
```

No options. Always plain text.

---

## `dinobase serve`

Start the MCP server (stdio transport).

```bash
dinobase serve [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--sync` | off | Enable background sync |
| `--sync-interval` | `1h` | Sync interval |

```bash
dinobase serve                              # MCP server only
dinobase serve --sync --sync-interval 30m   # with background sync
```

---

## `dinobase confirm <mutation_id>`

Confirm and execute a pending mutation.

```bash
dinobase confirm <mutation_id>
```

Mutations submitted via `dinobase query "UPDATE ..."` return a preview with a `mutation_id`. Use this command to execute it.

```bash
dinobase query "UPDATE stripe.customers SET name = 'Acme' WHERE id = 'cus_123'"
# Returns preview with mutation_id
dinobase confirm mut_abc123def456
```

---

## `dinobase cancel <mutation_id>`

Cancel a pending mutation without executing it.

```bash
dinobase cancel <mutation_id>
```

---

## `dinobase auth <type>`

Connect a connector via OAuth (browser-based authorization).

```bash
dinobase auth <connector_type> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--name` | Custom name for the connector (defaults to type) |
| `--proxy-url` | OAuth proxy URL (or set `DINOBASE_OAUTH_PROXY_URL`) |

Opens your browser to authorize Dinobase to access the upstream service. Tokens are stored locally and refreshed automatically on sync.

```bash
dinobase auth hubspot
dinobase auth salesforce --name my_salesforce
```

---

## `dinobase mcp-config [client]`

Print MCP configuration for Claude Code, Claude Desktop, or Cursor.

```bash
dinobase mcp-config [CLIENT]
```

| Argument | Description |
|----------|-------------|
| `claude-desktop` | Config for `~/.claude/claude_desktop_config.json` |
| `claude-code` | Config for `.mcp.json` (project root) |
| `cursor` | Config for `.cursor/mcp.json` (project root) |

Without arguments, prints configs for all three clients.

```bash
dinobase mcp-config                # show all configs
dinobase mcp-config claude-desktop # Claude Desktop only
dinobase mcp-config claude-code    # Claude Code only
dinobase mcp-config cursor         # Cursor only
```

---

## `dinobase mcp`

Interact with connected MCP servers. MCP server data is automatically synced into DuckDB tables (schema: server name, table: tool name), so prefer `dinobase query` for reads. Use `mcp call` for tools that need arguments or for write operations.

### `dinobase mcp servers`

List all connected MCP servers with their tool counts.

```bash
dinobase mcp servers [--pretty]
```

### `dinobase mcp instructions <server>`

Show a server's info and usage instructions.

```bash
dinobase mcp instructions <server> [--pretty]

dinobase mcp instructions posthog_mcp
```

### `dinobase mcp info <server>[.tool]`

List all tools on a server, or show the full schema (parameters, types) for one tool.

```bash
dinobase mcp info <server>[.tool] [--pretty]

dinobase mcp info posthog_mcp           # list all tools
dinobase mcp info posthog_mcp.list_projects  # show one tool's schema
```

### `dinobase mcp search "<pattern>"`

Regex search tool names and descriptions across all connected MCP servers.

```bash
dinobase mcp search "<pattern>" [--pretty]

dinobase mcp search "dashboard"
dinobase mcp search "list.*"
```

### `dinobase mcp call <server.tool> [args_json]`

Call a tool on a connected MCP server with optional JSON arguments.

```bash
dinobase mcp call <server.tool> ['{"arg": "value"}'] [--pretty]

dinobase mcp call posthog_mcp.list_projects
dinobase mcp call posthog_mcp.dashboard-get '{"id": 1118504}'
```

---

## `dinobase connector create <name>`

Scaffold a local custom connector YAML config.

```bash
dinobase connector create <name> [OPTIONS]
```

**REST connector options:**

| Option | Description |
|--------|-------------|
| `--url` | Base URL for the API |
| `--auth-type` | Authentication type: `bearer`, `http_basic`, `api_key_header` (default: `bearer`) |
| `--endpoint` | Endpoint path (e.g., `projects/123/feature_flags/`) |
| `--data-selector` | JSON path to data array (default: `$` for root) |
| `--mode` | Fetch mode: `live`, `sync`, `auto` (default: `auto`) |

**MCP connector options:**

| Option | Description |
|--------|-------------|
| `--transport` | MCP transport type: `stdio`, `sse`, `streamable_http` |
| `--command` | Full command string for stdio transport (e.g., `npx -y @modelcontextprotocol/server-filesystem /data`) |
| `--url` | Server URL for `sse` and `streamable_http` transports |
| `--mode` | Fetch mode: `live`, `sync` (default: `live`) |

Creates `~/.dinobase/connectors/<name>.yaml`. See [Custom REST Connectors](/docs/connectors/custom-rest/) and [MCP Server Connectors](/docs/connectors/mcp/).

```bash
# REST connector
dinobase connector create posthog_flags \
  --url "https://app.posthog.com/api/" \
  --endpoint "projects/123/feature_flags/" \
  --data-selector results

# MCP connector (stdio)
dinobase connector create posthog_mcp \
  --transport stdio \
  --command "npx -y @posthog/mcp-server"

# MCP connector (SSE)
dinobase connector create my_server \
  --transport sse \
  --url "https://server/sse"
```

---

## `dinobase connector list`

List all local custom connectors.

```bash
dinobase connector list [--pretty]
```

---

## `dinobase connector validate <name>`

Validate a local connector YAML config for required fields and credential placeholders.

```bash
dinobase connector validate my_api
```

---

## `dinobase connector edit <name>`

Open a local connector config in `$EDITOR`.

```bash
dinobase connector edit my_api
```

---

## Output format

All data commands (`status`, `query`, `describe`) output JSON by default, optimized for agent consumption. Add `--pretty` for human-readable tables.
