---
title: CrewAI Integration
description: Use Dinobase tools in CrewAI agents to query business data across 100+ sources.
---

Dinobase provides [CrewAI](https://www.crewai.com) tools that let your agents query business data from 100+ SaaS APIs, databases, and files via SQL.

## Install

```bash
pip install crewai dinobase
```

Set up your data sources:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase add hubspot --api-key pat-...
dinobase sync
```

See [Connecting Sources](/guides/connecting-sources/) for the full list of 100+ supported sources, and [Syncing & Scheduling](/guides/syncing/) for background sync options.

## Tools

Four tools are available:

| Tool | Description |
|------|-------------|
| `dinobase_query` | Execute SQL queries (DuckDB dialect) |
| `dinobase_describe` | Get table schema, types, and sample data |
| `dinobase_list_sources` | List connected sources with freshness status |
| `dinobase_refresh` | Re-sync a stale data source |

## Quick Start

```python
from crewai import Agent, Crew, Process, Task
from integrations.crewai.tools import (
    dinobase_query,
    dinobase_list_sources,
    dinobase_describe,
)

analyst = Agent(
    role="Data Analyst",
    goal="Answer business questions by querying data with SQL",
    backstory="You query business data across CRM, billing, and support tools.",
    tools=[dinobase_list_sources, dinobase_describe, dinobase_query],
)

task = Task(
    description="Which customers have overdue invoices but no recent support tickets?",
    expected_output="A list of customers with supporting data.",
    agent=analyst,
)

crew = Crew(
    agents=[analyst],
    tasks=[task],
    process=Process.sequential,
)

result = crew.kickoff()
print(result)
```

## How It Works

The tools wrap Dinobase's Python API (`QueryEngine`). When the agent calls `dinobase_query`, it executes SQL against your local DuckDB database containing synced data from all your sources.

The typical agent workflow:

1. `dinobase_list_sources` — discover what data is available
2. `dinobase_describe` — understand table schemas before writing SQL
3. `dinobase_query` — execute cross-source SQL queries
4. Present and analyze the results

Cross-source JOINs work via shared columns (email, company name, IDs). Tables are referenced as `schema.table` (e.g., `stripe.customers`, `hubspot.contacts`).

## Example Crew

See the [example crew](https://github.com/DinobaseHQ/dinobase/tree/main/integrations/crewai/examples) for a complete data analyst agent:

```bash
python examples/data_analyst_crew.py "What is our monthly revenue trend?"
```

## Next steps

- [Getting Started](/getting-started/) — Full setup walkthrough
- [Connecting Sources](/guides/connecting-sources/) — Add your business data
- [Querying Data](/guides/querying/) — SQL patterns and cross-source joins
- [Syncing & Scheduling](/guides/syncing/) — Keep data fresh
- [Schema Annotations](/guides/annotations/) — Add context for AI agents
- [Python API Reference](/reference/python-api/) — QueryEngine and SyncEngine
