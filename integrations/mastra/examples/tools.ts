// Mastra custom tools wrapping Dinobase CLI (alternative to MCP)
// Use this if you want more control over tool behavior

import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { execSync } from "child_process";

function runDinobase(args: string[]): string {
  return execSync(`dinobase ${args.join(" ")}`, {
    encoding: "utf-8",
    timeout: 30000,
  });
}

export const dinobaseQuery = createTool({
  id: "dinobase-query",
  description:
    "Execute a SQL query against Dinobase (DuckDB dialect). " +
    "Tables are referenced as schema.table (e.g., stripe.customers). " +
    "Cross-source JOINs work via shared columns like email.",
  inputSchema: z.object({
    sql: z.string().describe("SQL query to execute"),
    maxRows: z
      .number()
      .default(200)
      .describe("Maximum rows to return (default 200, max 10000)"),
  }),
  outputSchema: z.object({
    result: z.string(),
  }),
  execute: async ({ sql, maxRows }) => ({
    result: runDinobase(["query", JSON.stringify(sql), "--max-rows", String(maxRows)]),
  }),
});

export const dinobaseListSources = createTool({
  id: "dinobase-list-sources",
  description:
    "List all connected Dinobase data sources with tables, row counts, and freshness. " +
    "Use this first to understand what business data is available.",
  inputSchema: z.object({}),
  outputSchema: z.object({
    result: z.string(),
  }),
  execute: async () => ({
    result: runDinobase(["status"]),
  }),
});

export const dinobaseDescribe = createTool({
  id: "dinobase-describe",
  description:
    "Describe a table's columns, types, annotations, and sample data. " +
    "Use this before writing queries to understand column names and types.",
  inputSchema: z.object({
    table: z
      .string()
      .describe("Table reference as schema.table (e.g., stripe.customers)"),
  }),
  outputSchema: z.object({
    result: z.string(),
  }),
  execute: async ({ table }) => ({
    result: runDinobase(["describe", table]),
  }),
});

export const dinobaseRefresh = createTool({
  id: "dinobase-refresh",
  description:
    "Re-sync a data source to get fresh data. " +
    "Use when data might be stale and you need up-to-date results.",
  inputSchema: z.object({
    sourceName: z
      .string()
      .describe("Name of the source to refresh (e.g., stripe, hubspot)"),
  }),
  outputSchema: z.object({
    result: z.string(),
  }),
  execute: async ({ sourceName }) => ({
    result: runDinobase(["refresh", sourceName]),
  }),
});

export const allTools = {
  dinobaseQuery,
  dinobaseListSources,
  dinobaseDescribe,
  dinobaseRefresh,
};
