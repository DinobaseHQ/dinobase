// Next.js API route: app/api/chat/route.ts
// Streams AI responses with Dinobase tools available via MCP

import { streamText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { createMCPClient } from '@ai-sdk/mcp';
import { Experimental_StdioMCPTransport } from '@ai-sdk/mcp/mcp-stdio';

export async function POST(req: Request) {
  const { messages } = await req.json();

  // Connect to Dinobase MCP server via stdio
  const dinobase = await createMCPClient({
    transport: new Experimental_StdioMCPTransport({
      command: 'dinobase',
      args: ['serve'],
    }),
  });

  // Discover all Dinobase tools (query, describe, list_sources, etc.)
  const tools = await dinobase.tools();

  const result = streamText({
    model: anthropic('claude-sonnet-4-6'),
    system: `You are a helpful data analyst. When the user asks about business data,
use the Dinobase tools to query across their connected sources.

Workflow:
1. Use list_sources to see what data is available
2. Use describe to understand table schemas before querying
3. Use query to run SQL (DuckDB dialect, tables are schema.table)
4. Present results clearly`,
    messages,
    tools,
  });

  result.onFinish(() => dinobase.close());

  return result.toDataStreamResponse();
}
