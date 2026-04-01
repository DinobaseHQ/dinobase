---
title: Pydantic AI
description: Use Dinobase tools in Pydantic AI agents to query business data with type safety.
---

Dinobase provides a [Pydantic AI](https://ai.pydantic.dev) toolset that lets your agents query business data from 100+ sources with full type safety and dependency injection.

## Install

```bash
pip install "dinobase[pydantic-ai]"
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

Use the pre-configured agent:

```python
from dinobase.integrations.pydantic_ai.tools import DinobaseDeps, dinobase_agent

result = dinobase_agent.run_sync(
    "Which customers have overdue invoices?",
    deps=DinobaseDeps(),
)
print(result.output)
```

## Toolset on Your Own Agent

Attach the `dinobase_tools` toolset to any Pydantic AI agent:

```python
from pydantic_ai import Agent
from dinobase.integrations.pydantic_ai.tools import DinobaseDeps, dinobase_tools

agent = Agent(
    "anthropic:claude-sonnet-4-6",
    deps_type=DinobaseDeps,
    toolsets=[dinobase_tools],
    instructions="You are a financial analyst. Be concise.",
)

result = agent.run_sync("What is our MRR trend?", deps=DinobaseDeps())
print(result.output)
```

## Tools

The `dinobase_tools` toolset provides four tools:

| Tool | Description |
|------|-------------|
| `dinobase_query` | Execute SQL queries (DuckDB dialect) |
| `dinobase_describe` | Get table schema, types, and sample data |
| `dinobase_list_sources` | List connected sources with freshness status |
| `dinobase_refresh` | Re-sync a stale data source |

All tools use `RunContext[DinobaseDeps]` for type-safe dependency injection. The `DinobaseDeps` dataclass lazily initializes the Dinobase `QueryEngine`.

## How It Works

Tools wrap Dinobase's Python API via Pydantic AI's `FunctionToolset`. Dependencies are injected through `RunContext[DinobaseDeps]`, which provides access to the `QueryEngine`.

The typical agent workflow:

1. `dinobase_list_sources` — discover available data
2. `dinobase_describe` — understand table schemas
3. `dinobase_query` — run cross-source SQL queries
4. Present and analyze results

## Example

See the [example agent](https://github.com/DinobaseHQ/dinobase/tree/main/integrations/pydantic-ai/examples):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/analyst.py "Which deals closed this quarter?"
```

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connecting Sources](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [Python API Reference](/docs/reference/python-api/) — QueryEngine and SyncEngine
