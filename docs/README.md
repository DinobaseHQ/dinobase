# Introduction

Dinobase is the SQL query layer for agent stacks. It connects 100+ business data connectors and makes them queryable via a unified DuckDB interface — agents write SQL, cross-connector JOINs work natively.

Agent stacks built on per-connector tool calls have a structural gap: agents can't `JOIN` across APIs, have no semantic context to interpret field values, and receive paginated JSON that fills context windows. Dinobase fills that gap. In [benchmarks across 11 LLMs](project/benchmarks.md): **91% accuracy vs 35%, 3x faster, 16x cheaper per correct answer.**

## Why Dinobase

### Connect in minutes

Add Stripe, HubSpot, Postgres, or parquet files with one command. 100+ connectors supported.

### Cross-connector queries

JOIN Stripe customers with HubSpot deals with product analytics. Questions that required a data team now have instant answers.

### Semantic layer

After every sync, a Claude agent automatically annotates your data: table descriptions, column docs, PII flags, and relationship graphs. Agents know what every field means before writing a query.

### Accurate answers

Semantic context + complete data = 91% query accuracy vs 35% for bare MCP tools, across 10+ LLMs.

### MCP server proxy

Connect any MCP server as a connector. Read-only tools are auto-discovered and synced as SQL tables. Call any tool directly from the CLI, Python API, or via `exec_code` from an agent.

## Next steps

- [Getting Started](getting-started.md) — install, connect your first connector, run your first query
- [Semantic Layer](guides/annotations.md) — auto-annotation, relationship graphs, PII detection
- [Connectors](guides/connecting-sources.md) — all 100+ supported connector types
- [MCP Integration](integrations/mcp.md) — use Dinobase with Claude, Cursor, and other agents
