---
title: LangChain / LangGraph
description: Use Dinobase tools in LangChain and LangGraph agents to query business data across 100+ connectors.
---

Dinobase provides a [LangChain](https://python.langchain.com) toolkit that lets your agents query business data from 100+ SaaS APIs, databases, and files via SQL.

## Install

```bash
pip install langchain langchain-anthropic langgraph dinobase
```

Set up your connectors:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connectors](/docs/guides/connecting-sources/) for the full list of 100+ supported connectors, and [Syncing & Scheduling](/docs/guides/syncing/) for background sync options.

## Tools

The `DinobaseToolkit` provides four tools:

| Tool | Description |
|------|-------------|
| `dinobase_query` | Execute SQL queries (DuckDB dialect) |
| `dinobase_describe` | Get table schema, types, and sample data |
| `dinobase_list_connectors` | List configured connectors with freshness status |
| `dinobase_refresh` | Re-sync a stale connector |

## LangGraph Agent

```python
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from integrations.langchain.toolkit import DinobaseToolkit

model = ChatAnthropic(model="claude-sonnet-4-6")
toolkit = DinobaseToolkit()

agent = create_react_agent(
    model=model,
    tools=toolkit.get_tools(),
    prompt="You are a data analyst with access to Dinobase.",
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "Which customers churned last quarter?"}]
})
print(result["messages"][-1].content)
```

## Standalone Tool Binding

You can also bind tools directly to a model without a full agent:

```python
from langchain_anthropic import ChatAnthropic
from integrations.langchain.toolkit import DinobaseToolkit

model = ChatAnthropic(model="claude-sonnet-4-6")
toolkit = DinobaseToolkit()

model_with_tools = model.bind_tools(toolkit.get_tools())
response = model_with_tools.invoke("What connectors are available?")
```

## How It Works

The toolkit wraps Dinobase's Python API (`QueryEngine`). When the agent calls `dinobase_query`, it executes SQL against your local DuckDB database containing synced data from all configured connectors.

The typical agent workflow:

1. `dinobase_list_connectors` — discover available data
2. `dinobase_describe` — understand table schemas
3. `dinobase_query` — run cross-connector SQL queries
4. Present and analyze results

Cross-source JOINs work via shared columns (email, company name, IDs). Tables are referenced as `schema.table` (e.g., `stripe.customers`, `hubspot.contacts`).

## Example

See the [example agent](https://github.com/DinobaseHQ/dinobase/tree/main/integrations/langchain/examples) for a complete LangGraph ReAct agent:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/react_agent.py "What is our monthly revenue trend?"
```

## Next steps

- [Getting Started](/docs/getting-started/) — Full setup walkthrough
- [Connectors](/docs/guides/connecting-sources/) — Add your business data
- [Querying Data](/docs/guides/querying/) — SQL patterns and cross-connector joins
- [Syncing & Scheduling](/docs/guides/syncing/) — Keep data fresh
- [Schema Annotations](/docs/guides/annotations/) — Add context for AI agents
- [Python API Reference](/docs/reference/python-api/) — QueryEngine and SyncEngine
