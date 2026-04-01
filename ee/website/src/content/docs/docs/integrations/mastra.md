---
title: Mastra
description: Use Dinobase with Mastra, the TypeScript AI agent framework, via native MCP support.
---

Dinobase integrates with [Mastra](https://mastra.ai) via MCP. Mastra has first-class MCP support, so Dinobase's MCP server works with zero adapter code.

## Install

```bash
npm install @mastra/core @mastra/mcp @ai-sdk/anthropic zod
pip install dinobase
```

Set up your data sources:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connecting Sources](/docs/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/docs/guides/syncing/) for background sync options.

## Quick Start

```typescript
import { Agent } from "@mastra/core";
import { MCPClient } from "@mastra/mcp";
import { anthropic } from "@ai-sdk/anthropic";

// Connect to Dinobase MCP server
const mcp = new MCPClient({
  id: "dinobase-mcp",
  servers: {
    dinobase: {
      command: "dinobase",
      args: ["serve"],
    },
  },
});

// All 7 Dinobase tools discovered automatically
const agent = new Agent({
  id: "data-analyst",
  name: "Data Analyst",
  instructions: "You are a data analyst. Query business data via SQL.",
  model: anthropic("claude-sonnet-4-6"),
  tools: await mcp.listTools(),
});

const response = await agent.generate(
  "Which customers have overdue invoices?"
);
console.log(response.text);

await mcp.disconnect();
```

## How It Works

Mastra's `MCPClient` spawns the Dinobase MCP server as a subprocess (`dinobase serve`) and communicates via stdio. All 7 Dinobase MCP tools are discovered automatically and made available to the agent.

This is the same MCP server used by [Claude Desktop](/docs/integrations/claude-desktop/) and [Vercel AI SDK](/docs/integrations/vercel-ai/) — same tools, same data, different framework.

## Available Tools

Via MCP, the agent gets access to:

| Tool | Description |
|------|-------------|
| `query` | Execute SQL queries (DuckDB dialect) |
| `describe` | Get table schema, types, and sample data |
| `list_sources` | List connected sources with freshness status |
| `refresh` | Re-sync a stale data source |
| `confirm` | Execute a pending mutation (write-back) |
| `confirm_batch` | Execute multiple pending mutations |
| `cancel` | Cancel a pending mutation |

## Custom Tools (Alternative)

If you want more control over tool behavior, you can wrap the Dinobase CLI using `createTool()`:

```typescript
import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { execSync } from "child_process";

export const dinobaseQuery = createTool({
  id: "dinobase-query",
  description: "Execute SQL against Dinobase",
  inputSchema: z.object({
    sql: z.string().describe("SQL query to execute"),
  }),
  outputSchema: z.object({ result: z.string() }),
  execute: async ({ sql }) => ({
    result: execSync(`dinobase query ${JSON.stringify(sql)}`, {
      encoding: "utf-8",
    }),
  }),
});
```

See `examples/tools.ts` for all four tool wrappers.

## Background Sync

Keep data fresh while the MCP server runs:

```typescript
const mcp = new MCPClient({
  id: "dinobase-mcp",
  servers: {
    dinobase: {
      command: "dinobase",
      args: ["serve", "--sync", "--sync-interval", "30m"],
    },
  },
});
```

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connecting Sources](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [MCP Integration](/docs/integrations/mcp/) — How the MCP server works
- [MCP Tools Reference](/docs/reference/mcp-tools/) — Detailed tool schemas
- [Example code](https://github.com/DinobaseHQ/dinobase/tree/main/integrations/mastra/examples)
