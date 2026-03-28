# Dinobase + LangChain / LangGraph

LangChain toolkit that gives your agents access to business data from 100+ sources via SQL.

## Install

```bash
pip install langchain langchain-anthropic langgraph dinobase
```

## Setup

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

## Usage

### Toolkit

```python
from integrations.langchain.toolkit import DinobaseToolkit

toolkit = DinobaseToolkit()
tools = toolkit.get_tools()
```

### LangGraph ReAct Agent

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

### Standalone Tools

```python
from langchain_anthropic import ChatAnthropic
from integrations.langchain.toolkit import DinobaseToolkit

model = ChatAnthropic(model="claude-sonnet-4-6")
toolkit = DinobaseToolkit()

# Bind tools directly to a model
model_with_tools = model.bind_tools(toolkit.get_tools())
response = model_with_tools.invoke("What data sources are available?")
```

## Available Tools

| Tool | Description |
|------|-------------|
| `dinobase_query` | Execute SQL queries (DuckDB dialect). Cross-source JOINs supported. |
| `dinobase_list_sources` | List all connected sources with tables, row counts, freshness. |
| `dinobase_describe` | Get table schema, column types, annotations, sample data. |
| `dinobase_refresh` | Re-sync a source to get fresh data. |

## Example

See `examples/react_agent.py` for a complete LangGraph agent:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/react_agent.py "What is our monthly revenue trend?"
```
