# Dinobase + Vercel AI SDK

Use Dinobase as an MCP tool server with the Vercel AI SDK. Your AI app gets instant access to business data from 100+ sources via SQL.

**No adapter code needed** — Dinobase's MCP server works natively with the AI SDK's MCP client.

## Quick Start

### 1. Install dependencies

```bash
npm install ai @ai-sdk/anthropic @ai-sdk/mcp
pip install dinobase
```

### 2. Set up Dinobase

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase sync
```

### 3. Use in your Next.js API route

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

That's it. The AI SDK automatically discovers all 7 Dinobase MCP tools (query, describe, list_sources, refresh, confirm, confirm_batch, cancel).

## Available Tools

The MCP server exposes these tools to the AI model:

| Tool | Description |
|------|-------------|
| `query` | Execute SQL queries (DuckDB dialect) |
| `describe` | Get table schema, types, and sample data |
| `list_sources` | List connected sources with freshness status |
| `refresh` | Re-sync a stale data source |
| `confirm` | Execute a pending mutation (write-back) |
| `confirm_batch` | Execute multiple pending mutations |
| `cancel` | Cancel a pending mutation |

## Examples

See the `examples/` directory:

- **`route.ts`** — Next.js API route with streaming
- **`generate.ts`** — Node.js script with `generateText()`

## Notes

- `Experimental_StdioMCPTransport` is Node.js only (not edge runtime)
- Always close the MCP client when done (`dinobase.close()`)
- For production, consider running Dinobase as a persistent process with `dinobase serve --sync` for background data syncing
