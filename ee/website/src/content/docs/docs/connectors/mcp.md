---
title: MCP Server Connectors
description: Connect any MCP server as a Dinobase connector. Auto-discovers read-only tools and syncs their output as SQL tables.
---

Connect any MCP server (stdio, SSE, or streamable HTTP) as a connector. Dinobase discovers the server's read-only tools, calls them, and caches the results as JSON files exposed as DuckDB views — queryable with the same SQL interface as any other connector.

This gives you **two complementary interfaces** to the same MCP server:

- **SQL**, for reads: synced data is available as `connector.tool_name` tables
- **Direct tool calls**, for writes or parameterized queries: `dinobase mcp call`

## Quick start

The easiest way to add an MCP server is through the setup UI's registry browser:

```bash
dinobase setup
```

In the **Add a source** section, click **Browse MCP registry…**. This fetches
the reference server list from
[`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers),
lets you fill in any required env vars, and writes the YAML to
`~/.dinobase/connectors/<name>.yaml` in one click. See the
[Setup UI guide](/docs/guides/setup-ui/) for the full walkthrough.

Or use the CLI directly:

```bash
# stdio (local process)
dinobase connector create posthog_mcp \
  --transport stdio \
  --command "npx -y @posthog/mcp-server"

# SSE
dinobase connector create my_server \
  --transport sse \
  --url "https://server/sse"

# Streamable HTTP
dinobase connector create my_server \
  --transport streamable_http \
  --url "https://server/mcp"

dinobase sync posthog_mcp
dinobase query "SELECT * FROM posthog_mcp.list_projects LIMIT 10"
```

## Connector YAML format

Configs live at `~/.dinobase/connectors/<name>.yaml`. The `transport` block is what distinguishes an MCP connector from a custom REST connector:

```yaml
name: posthog_mcp
description: "PostHog MCP server"
mode: live  # live | sync (default: live for MCP)

transport:
  type: stdio        # stdio | sse | streamable_http
  command: npx
  args:
    - "-y"
    - "@posthog/mcp-server"

# Optional: only sync these specific tools.
# Default: all read-only tools are auto-discovered.
tools:
  - list_projects
  - list_feature_flags
```

For SSE and streamable HTTP, use `url` instead of `command`/`args`:

```yaml
transport:
  type: sse
  url: "https://my-mcp-server.example.com/sse"
  headers:
    Authorization: "Bearer my_token"
```

## How read-only tools are selected

When syncing, Dinobase only calls tools that are safe to call without context:

1. **User allowlist** — if `tools:` is set in the YAML, only those tools are called
2. **MCP ToolAnnotations** — tools with `readOnlyHint: true` are included; `destructiveHint: true` are excluded
3. **Name heuristics** — tools starting with `list_`, `get_`, `search_`, `read_`, or `fetch_` are included; tools starting with `create_`, `update_`, `delete_`, `set_`, `send_`, `remove_`, or `put_` are excluded
4. **Required parameters** — tools with required parameters are skipped (they can't be called without context)

## Calling tools directly

Use `dinobase mcp call` for tools that need arguments or for write operations:

```bash
# Browse available tools
dinobase mcp servers --pretty
dinobase mcp info posthog_mcp --pretty
dinobase mcp search "dashboard" --pretty

# Call a tool with arguments
dinobase mcp call posthog_mcp.dashboard-get '{"id": 1118504}'
```

Or use the Python API:

```python
from dinobase.mcp import call, search

result = call("posthog_mcp.dashboard-get", id=1118504)
matches = search("dashboard")
```

## Transport types

| Type | When to use |
|------|-------------|
| `stdio` | Local process (e.g., an npm package run via `npx`) |
| `sse` | Remote server exposing a legacy SSE endpoint |
| `streamable_http` | Remote server exposing a streamable HTTP endpoint |

## See also

- [Connectors guide](/docs/guides/connecting-sources/) — overview of all connector types
- [`dinobase mcp` CLI reference](/docs/reference/cli/#dinobase-mcp) — all subcommands
- [Python MCP client API](/docs/reference/python-api/#mcp-client) — `call`, `tools`, `servers`, `search`, `instructions`
- [`exec_code` MCP tool](/docs/reference/mcp-tools/#exec_code) — let agents call MCP tools via Python
- [Custom REST connectors](/docs/connectors/custom-rest/) — for plain REST APIs instead of MCP
