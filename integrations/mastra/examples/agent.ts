// Mastra agent with Dinobase via MCP
// Run: npx tsx agent.ts

import { Agent } from "@mastra/core";
import { MCPClient } from "@mastra/mcp";
import { anthropic } from "@ai-sdk/anthropic";

async function main() {
  // Connect to Dinobase MCP server via stdio
  const mcp = new MCPClient({
    id: "dinobase-mcp",
    servers: {
      dinobase: {
        command: "dinobase",
        args: ["serve"],
      },
    },
  });

  // All 7 Dinobase tools are discovered automatically
  const tools = await mcp.listTools();

  const agent = new Agent({
    id: "data-analyst",
    name: "Data Analyst",
    instructions: `You are a data analyst with access to Dinobase — a SQL database
containing business data synced from multiple SaaS tools.

Workflow:
1. Use dinobase_list_sources to see what data is available
2. Use dinobase_describe on relevant tables to understand schemas
3. Use dinobase_query to run SQL (DuckDB dialect, tables are schema.table)
4. Present results clearly with your analysis`,
    model: anthropic("claude-sonnet-4-6"),
    tools,
  });

  const question =
    process.argv[2] || "What data sources are connected?";
  const response = await agent.generate(question);

  console.log(response.text);

  await mcp.disconnect();
}

main();
