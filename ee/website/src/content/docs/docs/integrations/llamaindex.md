---
title: LlamaIndex
description: Use Dinobase tools in LlamaIndex agents to query business data across 100+ connectors.
---

Dinobase provides a [LlamaIndex](https://www.llamaindex.ai) tool spec that lets your agents query business data from 100+ SaaS APIs, databases, and files via SQL.

## Install

```bash
pip install llama-index llama-index-llms-anthropic dinobase
```

Set up your connectors:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connectors](/docs/guides/connecting-sources/) for the full list of 100+ supported connectors, and [Syncing & Scheduling](/docs/guides/syncing/) for background sync options.

## Quick Start

```python
from llama_index.core.agent import ReActAgent
from llama_index.llms.anthropic import Anthropic
from integrations.llamaindex.tool_spec import DinobaseToolSpec

llm = Anthropic(model="claude-sonnet-4-6")
tool_spec = DinobaseToolSpec()

agent = ReActAgent.from_tools(
    tool_spec.to_tool_list(),
    llm=llm,
    verbose=True,
)

response = agent.chat("Which customers have overdue invoices?")
print(response.response)
```

## Tools

The `DinobaseToolSpec` provides four tools via `to_tool_list()`:

| Tool | Description |
|------|-------------|
| `dinobase_query` | Execute SQL queries (DuckDB dialect) |
| `dinobase_describe` | Get table schema, types, and sample data |
| `dinobase_list_connectors` | List configured connectors with freshness status |
| `dinobase_refresh` | Re-sync a stale connector |

## How It Works

The `DinobaseToolSpec` extends LlamaIndex's `BaseToolSpec`. Each method listed in `spec_functions` becomes a `FunctionTool` when you call `to_tool_list()`. The agent discovers tools via their docstrings and `Annotated` type hints.

The typical agent workflow:

1. `dinobase_list_connectors` — discover available data
2. `dinobase_describe` — understand table schemas
3. `dinobase_query` — run cross-connector SQL queries
4. Present and analyze results

Cross-source JOINs work via shared columns (email, company name, IDs). Tables are referenced as `schema.table` (e.g., `stripe.customers`, `hubspot.contacts`).

## Example

See the [example agent](https://github.com/DinobaseHQ/dinobase/tree/main/integrations/llamaindex/examples):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/react_agent.py "What deals closed this quarter?"
```

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connectors](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-connector joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [Python API Reference](/docs/reference/python-api/) — QueryEngine and SyncEngine
