"""Example: LangGraph ReAct agent powered by Dinobase.

Run:
    pip install langchain langchain-anthropic langgraph dinobase
    export ANTHROPIC_API_KEY=sk-ant-...
    dinobase init && dinobase add stripe --api-key sk_test_... && dinobase sync
    python react_agent.py "Which customers have overdue invoices?"
"""

from __future__ import annotations

import sys

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

sys.path.insert(0, "..")
from toolkit import DinobaseToolkit


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "What data sources are connected?"

    model = ChatAnthropic(model="claude-sonnet-4-6")
    toolkit = DinobaseToolkit()
    tools = toolkit.get_tools()

    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=(
            "You are a data analyst with access to Dinobase — a SQL database "
            "containing business data synced from multiple SaaS tools.\n\n"
            "Workflow:\n"
            "1. Use dinobase_list_sources to see what data is available\n"
            "2. Use dinobase_describe on relevant tables to understand schemas\n"
            "3. Use dinobase_query to run SQL (DuckDB dialect, tables are schema.table)\n"
            "4. Present results clearly with your analysis"
        ),
    )

    result = agent.invoke({"messages": [{"role": "user", "content": question}]})

    # Print the final response
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
