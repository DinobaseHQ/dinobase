---
title: Python Execution (exec_code)
description: Let agents run Python against Dinobase internals — call MCP tools, reshape query results, and chain operations that don't fit in plain SQL.
---

`exec_code` is an MCP tool that runs arbitrary Python code with access to Dinobase internals. Agents use it when SQL isn't enough — calling external MCP tools, chaining multiple operations, or reshaping results in ways that are awkward to express in SQL.

It complements the SQL `query` tool rather than replacing it: SQL stays the primary read interface, and `exec_code` fills the gaps.

## When to reach for it

| Situation | Use this |
|-----------|----------|
| Filter/join/aggregate across synced tables | **`query`** (SQL) |
| Browse tools on a connected MCP server | **`dinobase mcp` CLI** or **`mcp call`** |
| Call one MCP tool with simple arguments | **`mcp call`** |
| Call multiple MCP tools and combine their output | **`exec_code`** |
| Reshape query results with Python logic (grouping, string parsing) | **`exec_code`** |
| Call an MCP tool that needs dynamic arguments built from a query | **`exec_code`** |
| Write-back mutations to upstream systems | **`query` with UPDATE/INSERT** (plus `confirm`) |

If the task is a read you could write as SQL, prefer SQL — it's cheaper in tokens and faster. Use `exec_code` when the logic genuinely needs Python.

## How the tool works

The MCP server exposes a single tool:

```
exec_code(code: str) -> str
```

The Python code runs in an isolated namespace with full access to the Python standard library and every installed package. To return a value, assign it to `result`:

```python
result = "hello"
```

If `result` is set, Dinobase serializes it to JSON (falling back to `str()` for non-JSON values) and returns it. If `result` is unset, the tool returns `{"status": "ok"}`. If the code raises, you get `{"error": "ExceptionType: message"}`.

State does not persist between calls — each invocation starts with a fresh namespace.

## Available APIs

Import these inside your `code` string — nothing is pre-imported:

```python
from dinobase.mcp import call, tools, servers, search, instructions
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine
from dinobase.query.mutations import MutationEngine
```

- **`dinobase.mcp`** — sync wrappers around connected MCP servers. See the [Python API reference](/docs/reference/python-api/#mcp-client).
- **`DinobaseDB` / `QueryEngine`** — same interfaces the CLI and MCP server use internally. See the [Python API reference](/docs/reference/python-api/).
- **`MutationEngine`** — programmatic write-back with the same preview/confirm flow.

## Examples

### Call an MCP tool with arguments

```python
from dinobase.mcp import call

result = call("posthog_mcp.dashboard-get", id=1118504)
```

### Chain two MCP calls

Fetch a list, then look up details for each item:

```python
from dinobase.mcp import call

dashboards = call("posthog_mcp.dashboards-get-all")
ids = [d["id"] for d in dashboards.get("structuredContent", {}).get("results", [])]

details = []
for dashboard_id in ids[:5]:
    detail = call("posthog_mcp.dashboard-get", id=dashboard_id)
    details.append(detail.get("structuredContent"))

result = details
```

### Combine SQL and an MCP call

Query the synced database, then call an upstream tool for each row:

```python
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine
from dinobase.mcp import call

with DinobaseDB() as db:
    rows = QueryEngine(db).execute(
        "SELECT id FROM hubspot.companies WHERE industry = 'SaaS' LIMIT 10"
    )["rows"]

enriched = []
for row in rows:
    detail = call("clearbit_mcp.company-lookup", domain=row["id"])
    enriched.append(detail.get("structuredContent"))

result = enriched
```

### Reshape results with Python

Group query results by a computed key that SQL can't easily express:

```python
from collections import defaultdict
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine

with DinobaseDB() as db:
    rows = QueryEngine(db).execute(
        "SELECT email, created FROM stripe.customers"
    )["rows"]

by_domain = defaultdict(list)
for row in rows:
    domain = row["email"].split("@")[-1] if row["email"] else "(none)"
    by_domain[domain].append(row["created"])

result = {d: len(v) for d, v in sorted(by_domain.items(), key=lambda kv: -len(kv[1]))}
```

### Discover what's available

```python
from dinobase.mcp import servers, search

result = {
    "servers": servers(),
    "dashboard_tools": search("dashboard"),
}
```

## Returning values

The returned value becomes the tool's JSON response. For agent-friendly output:

- Prefer plain dicts, lists, and primitives — they serialize cleanly.
- Strings become JSON strings. Integers, floats, and booleans pass through.
- Objects that aren't JSON-serializable fall back to `str()` via `json.dumps(..., default=str)`, then finally to a raw `str(output)` if that fails too.
- Setting `result = None` (or not setting `result`) returns `{"status": "ok"}` — use this for scripts whose side effects are the point (writes, refreshes).

## Errors

Exceptions come back as a single-field dict:

```json
{"error": "ValueError: id is required"}
```

The traceback isn't included — if you're debugging, print intermediate values and wrap risky sections in `try`/`except` yourself:

```python
try:
    data = call("my_server.fetch", id=123)
    result = {"ok": True, "rows": len(data.get("structuredContent", {}).get("items", []))}
except Exception as e:
    result = {"ok": False, "error": str(e)}
```

## Security considerations

`exec_code` runs with the same privileges as the MCP server process. There's no sandbox — the code can read any file, hit any network endpoint, or call any MCP server the Dinobase process has access to.

Only enable this tool on MCP servers you trust with the agents you trust. If you're running Dinobase locally for yourself, this is the same trust model as letting the agent run shell commands. If you're exposing Dinobase to a broader set of agents, consider disabling the MCP server's `exec_code` tool in your deployment.

## See also

- [MCP Tools Reference → exec_code](/docs/reference/mcp-tools/#exec_code) — the raw tool schema and response format
- [Python API → MCP Client](/docs/reference/python-api/#mcp-client) — `call`, `tools`, `servers`, `search`, `instructions`
- [MCP Server Connectors](/docs/connectors/mcp/) — connecting MCP servers so their tools are callable from `exec_code`
- [Querying Data](/docs/guides/querying/) — when SQL is the better choice
