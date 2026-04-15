---
title: Setup GUI
description: Configure Dinobase connectors and MCP servers from a local browser UI.
---

`dinobase setup` launches a bundled local GUI so you can add connectors (SaaS APIs, databases, files, MCP servers, and custom REST) without editing YAML by hand.

```bash
dinobase setup
```

The command starts an HTTP server on `127.0.0.1` at a random port and opens a
browser tab pointing at it. Everything runs on your machine — the GUI never
sends configuration over the network.

## What you can do

- **Add a connector** — browse the full registry of ~50 SaaS APIs, databases, and
  cloud-storage backends, fill in credentials, and save to `~/.dinobase/config.yaml`.
- **Custom REST connector** — point Dinobase at any REST API; the GUI writes
  a YAML connector under `~/.dinobase/connectors/`.
- **MCP servers** — add stdio, SSE, or streamable-HTTP MCP servers; the
  server's tools become queryable via `dinobase mcp call` and, for no-arg
  tools, auto-sync into DuckDB tables.
- **Browse the MCP registry** — click **Browse MCP registry…** to pull the
  list of reference servers from the official
  [`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers)
  repo, enter any required env vars (API keys, paths, etc.), and install one
  with a single click. The generated YAML is written to
  `~/.dinobase/connectors/<name>.yaml` just like a hand-added MCP server.
- **Disconnect a connector** — remove any configured connector with one click.

## Options

```bash
dinobase setup --port 7777     # bind a specific port instead of random
dinobase setup --no-browser    # print the URL but don't open a browser
```

The server stops on `Ctrl+C` or when you click the **Quit setup** button in
the GUI.

### Developing against a local UI

Set `DINOBASE_SETUP_UI_DIR=/path/to/ui` to serve a directory directly
from disk, with no network and no caching. The version pill shows
`UI dev (dev)`.

## When to use the CLI instead

The CLI (`dinobase add`, `dinobase auth`, `dinobase connector create`) still
works for agent workflows, scripts, and headless environments. The GUI is
for humans who'd rather point-and-click than remember flag names.
