# Dinobase + CrewAI

CrewAI tools that give your agents access to business data from 100+ sources via SQL.

## Install

```bash
pip install crewai dinobase
```

## Setup

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

## Usage

### Import the tools

```python
from integrations.crewai.tools import (
    dinobase_query,
    dinobase_list_sources,
    dinobase_describe,
    dinobase_refresh,
    all_tools,
)
```

### Add to your agent

```python
from crewai import Agent

analyst = Agent(
    role="Data Analyst",
    goal="Answer business questions using SQL",
    backstory="You query business data across CRM, billing, and support tools.",
    tools=[dinobase_list_sources, dinobase_describe, dinobase_query],
)
```

### Or use all tools at once

```python
analyst = Agent(
    role="Data Analyst",
    goal="Answer business questions using SQL",
    backstory="You query and manage business data across multiple sources.",
    tools=all_tools,
)
```

## Available Tools

| Tool | Description |
|------|-------------|
| `dinobase_query` | Execute SQL queries (DuckDB dialect). Cross-source JOINs supported. |
| `dinobase_list_sources` | List all connected sources with tables, row counts, freshness. |
| `dinobase_describe` | Get table schema, column types, annotations, sample data. |
| `dinobase_refresh` | Re-sync a source to get fresh data. |

## Example

See `examples/data_analyst_crew.py` for a complete working crew:

```bash
python examples/data_analyst_crew.py "Which customers churned but had open support tickets?"
```

## How It Works

The tools wrap Dinobase's Python API (`QueryEngine`, `SyncEngine`). Data stays local in DuckDB — no external API calls at query time. The agent writes SQL, Dinobase executes it, results come back as JSON.

The agent workflow is:
1. `dinobase_list_sources` — discover available data
2. `dinobase_describe` — understand table schemas
3. `dinobase_query` — run cross-source SQL
4. Present results
