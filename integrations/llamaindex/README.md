# Dinobase + LlamaIndex

LlamaIndex tool spec that gives your agents access to business data from 100+ sources via SQL.

## Install

```bash
pip install llama-index llama-index-llms-anthropic dinobase
```

## Setup

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

## Usage

### Tool spec

```python
from integrations.llamaindex.tool_spec import DinobaseToolSpec

tool_spec = DinobaseToolSpec()
tools = tool_spec.to_tool_list()
```

### ReAct Agent

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

response = agent.chat("Which customers churned last quarter?")
print(response.response)
```

### Individual tools

```python
from llama_index.core.tools import FunctionTool
from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine

engine = QueryEngine(DinobaseDB())

def query(sql: str) -> str:
    """Execute SQL against business data."""
    import json
    return json.dumps(engine.execute(sql), indent=2, default=str)

tool = FunctionTool.from_defaults(query, name="dinobase_query")
```

## Available Tools

| Tool | Description |
|------|-------------|
| `dinobase_query` | Execute SQL queries (DuckDB dialect). Cross-source JOINs supported. |
| `dinobase_list_sources` | List all connected sources with tables, row counts, freshness. |
| `dinobase_describe` | Get table schema, column types, annotations, sample data. |
| `dinobase_refresh` | Re-sync a source to get fresh data. |

## Example

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/react_agent.py "What is our monthly revenue trend?"
```
