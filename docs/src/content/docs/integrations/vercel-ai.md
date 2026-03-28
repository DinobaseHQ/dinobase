---
title: Vercel AI SDK
description: Use Dinobase as an MCP tool server with the Vercel AI SDK.
---

Dinobase integrates with the [Vercel AI SDK](https://sdk.vercel.ai) via MCP. No adapter code needed — the AI SDK's MCP client connects directly to Dinobase's MCP server.

## Install

```bash
npm install ai @ai-sdk/anthropic @ai-sdk/mcp
pip install dinobase
```

Set up Dinobase with your data sources:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase sync
```

See [Connecting Sources](/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/guides/syncing/) for background sync options.

## Next.js API Route

```typescript
// app/api/chat/route.ts
import { streamText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { createMCPClient } from '@ai-sdk/mcp';
import { Experimental_StdioMCPTransport } from '@ai-sdk/mcp/mcp-stdio';

export async function POST(req: Request) {
  const { messages } = await req.json();

  const dinobase = await createMCPClient({
    transport: new Experimental_StdioMCPTransport({
      command: 'dinobase',
      args: ['serve'],
    }),
  });

  const tools = await dinobase.tools();

  const result = streamText({
    model: anthropic('claude-sonnet-4-6'),
    messages,
    tools,
  });

  result.onFinish(() => dinobase.close());

  return result.toDataStreamResponse();
}
```

The AI SDK automatically discovers all 7 Dinobase MCP tools.

## Node.js Script

For scripts and CLI tools, use `generateText()`:

```typescript
import { generateText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { createMCPClient } from '@ai-sdk/mcp';
import { Experimental_StdioMCPTransport } from '@ai-sdk/mcp/mcp-stdio';

const dinobase = await createMCPClient({
  transport: new Experimental_StdioMCPTransport({
    command: 'dinobase',
    args: ['serve'],
  }),
});

const tools = await dinobase.tools();

const { text } = await generateText({
  model: anthropic('claude-sonnet-4-6'),
  prompt: 'Which customers have overdue invoices?',
  tools,
  maxSteps: 5,
});

console.log(text);
await dinobase.close();
```

## Available Tools

The MCP server exposes these tools to the AI model:

| Tool | Description |
|------|-------------|
| `query` | Execute SQL queries (DuckDB dialect) |
| `describe` | Get table schema, column types, and sample data |
| `list_sources` | List all connected sources with row counts and freshness |
| `refresh` | Re-sync a data source to get fresh data |
| `confirm` | Execute a pending mutation (write-back to source API) |
| `confirm_batch` | Execute multiple pending mutations |
| `cancel` | Cancel a pending mutation |

## Background Sync

To keep data fresh while the MCP server runs:

```typescript
const dinobase = await createMCPClient({
  transport: new Experimental_StdioMCPTransport({
    command: 'dinobase',
    args: ['serve', '--sync', '--sync-interval', '30m'],
  }),
});
```

## Notes

- `Experimental_StdioMCPTransport` runs in Node.js only (not edge runtime or browser)
- Always close the MCP client when done to clean up the subprocess
- The model sees dynamic instructions computed from your actual database state — it knows what sources and tables are available

## Next steps

- [Getting Started](/getting-started/) — Full setup walkthrough
- [Connecting Sources](/guides/connecting-sources/) — Add your business data
- [Querying Data](/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/guides/syncing/) — Keep data fresh
- [Schema Annotations](/guides/annotations/) — Add context for AI agents
- [MCP Integration](/integrations/mcp/) — How the MCP server works
- [MCP Tools Reference](/reference/mcp-tools/) — Detailed tool schemas
- [Example code](https://github.com/DinobaseHQ/dinobase/tree/main/integrations/vercel-ai/examples)
