---
title: OpenClaw Integration
description: Use Dinobase with OpenClaw, the open-source personal AI assistant.
---

Dinobase integrates with [OpenClaw](https://openclaw.ai) via a skill that teaches your OpenClaw agent to query business data using the Dinobase CLI.

## Install the skill

```bash
openclaw skills install dinobase
```

This installs the Dinobase skill from ClawHub. If `dinobase` isn't installed, OpenClaw will auto-install it via `uv`.

### Manual install

If you prefer to install manually:

```bash
pip install dinobase

mkdir -p ~/.openclaw/skills/dinobase
curl -o ~/.openclaw/skills/dinobase/SKILL.md \
  https://raw.githubusercontent.com/DinobaseHQ/dinobase/main/integrations/openclaw/SKILL.md
```

## Setup

Once the skill is installed, set up your data sources. You can either tell your agent:

> "Initialize Dinobase and connect my Stripe account with API key sk_test_..."

Or run the commands yourself:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connecting Sources](/docs/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/docs/guides/syncing/) for background sync options.

## Usage

Ask your OpenClaw agent data questions that span multiple tools:

> "Which customers churned last quarter but had declining usage AND open support tickets?"

The agent will:

1. Run `dinobase info` to see available sources and tables
2. Run `dinobase describe` on relevant tables to understand schemas
3. Write and execute SQL via `dinobase query`
4. Format and present the results

All Dinobase CLI commands output JSON by default, which the agent parses automatically.

## How it works

The OpenClaw skill teaches the agent to use the Dinobase CLI via the built-in `exec` tool. The agent runs shell commands like `dinobase query "SELECT ..."` and parses the JSON output.

This is the same interface used by Claude Code, Aider, and other shell-capable agents. The data and query engine are identical to the [MCP server](/docs/integrations/mcp/) -- just a different transport.

## What the agent can do

| Action | Command |
|--------|---------|
| See available data | `dinobase info` |
| Check source freshness | `dinobase status` |
| Describe a table | `dinobase describe stripe.customers` |
| Run SQL queries | `dinobase query "SELECT ..."` |
| Cross-source joins | SQL JOIN across schemas |
| Write data back | `dinobase query "UPDATE ..."` + `dinobase confirm` |
| Refresh stale data | `dinobase refresh stripe` |

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connecting Sources](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [CLI Reference](/docs/reference/cli/) — All commands and flags
