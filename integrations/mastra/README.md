# Dinobase + Mastra

Use Dinobase with [Mastra](https://mastra.ai), the TypeScript AI agent framework. Mastra has native MCP support, so Dinobase's MCP server works out of the box.

## Install

```bash
npm install @mastra/core @mastra/mcp @ai-sdk/anthropic zod
pip install dinobase
```

## Setup

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase sync
```

## Usage: MCP (Recommended)

Zero adapter code — Mastra's `MCPClient` connects directly to Dinobase's MCP server:

```typescript
import { Agent } from "@mastra/core";
import { MCPClient } from "@mastra/mcp";
import { anthropic } from "@ai-sdk/anthropic";

const mcp = new MCPClient({
  id: "dinobase-mcp",
  servers: {
    dinobase: {
      command: "dinobase",
      args: ["serve"],
    },
  },
});

const agent = new Agent({
  id: "data-analyst",
  name: "Data Analyst",
  instructions: "You are a data analyst. Query Dinobase for business insights.",
  model: anthropic("claude-sonnet-4-6"),
  tools: await mcp.listTools(),
});

const response = await agent.generate("Which customers churned last quarter?");
console.log(response.text);

await mcp.disconnect();
```

All 7 Dinobase MCP tools are discovered automatically: `query`, `describe`, `list_sources`, `refresh`, `confirm`, `confirm_batch`, `cancel`.

## Usage: Custom Tools (Alternative)

If you want more control, use the custom tool wrappers that call the Dinobase CLI:

```typescript
import { Agent } from "@mastra/core";
import { anthropic } from "@ai-sdk/anthropic";
import { allTools } from "./examples/tools";

const agent = new Agent({
  id: "data-analyst",
  name: "Data Analyst",
  instructions: "You are a data analyst with access to business data.",
  model: anthropic("claude-sonnet-4-6"),
  tools: allTools,
});
```

## Examples

- **`examples/agent.ts`** — MCP-based agent (recommended)
- **`examples/tools.ts`** — Custom `createTool()` wrappers calling Dinobase CLI

```bash
export ANTHROPIC_API_KEY=sk-ant-...
npx tsx examples/agent.ts "What is our monthly revenue trend?"
```
