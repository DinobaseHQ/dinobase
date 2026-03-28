// Node.js script: query Dinobase using Vercel AI SDK + MCP
// Run: npx tsx generate.ts

import { generateText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { createMCPClient } from '@ai-sdk/mcp';
import { Experimental_StdioMCPTransport } from '@ai-sdk/mcp/mcp-stdio';

async function main() {
  const dinobase = await createMCPClient({
    transport: new Experimental_StdioMCPTransport({
      command: 'dinobase',
      args: ['serve'],
    }),
  });

  try {
    const tools = await dinobase.tools();

    const { text } = await generateText({
      model: anthropic('claude-sonnet-4-6'),
      prompt: 'Which customers have overdue invoices? Show me the top 10 by amount.',
      tools,
      maxSteps: 5,
    });

    console.log(text);
  } finally {
    await dinobase.close();
  }
}

main();
