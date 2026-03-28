# Dinobase + Pydantic AI

Type-safe Pydantic AI toolset that gives your agents access to business data from 100+ sources via SQL.

## Install

```bash
pip install pydantic-ai dinobase
```

## Setup

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

## Usage

### Pre-configured agent

```python
from integrations.pydantic_ai.tools import DinobaseDeps, dinobase_agent

result = dinobase_agent.run_sync(
    "Which customers churned last quarter?",
    deps=DinobaseDeps(),
)
print(result.output)
```

### Toolset on your own agent

```python
from pydantic_ai import Agent
from integrations.pydantic_ai.tools import DinobaseDeps, dinobase_tools

agent = Agent(
    "anthropic:claude-sonnet-4-6",
    deps_type=DinobaseDeps,
    toolsets=[dinobase_tools],
    instructions="You are a financial analyst.",
)

result = agent.run_sync("What is our MRR trend?", deps=DinobaseDeps())
print(result.output)
```

### Individual tools on your agent

```python
from pydantic_ai import Agent, RunContext
from integrations.pydantic_ai.tools import DinobaseDeps

agent = Agent("anthropic:claude-sonnet-4-6", deps_type=DinobaseDeps)

@agent.tool
def query(ctx: RunContext[DinobaseDeps], sql: str) -> str:
    """Execute SQL against business data."""
    import json
    result = ctx.deps.get_engine().execute(sql)
    return json.dumps(result, indent=2, default=str)
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
python examples/analyst.py "What is our monthly revenue trend?"
```
