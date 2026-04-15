"""Example: LlamaIndex ReAct agent powered by Dinobase.

Run:
    pip install llama-index llama-index-llms-anthropic dinobase
    export ANTHROPIC_API_KEY=sk-ant-...
    dinobase init && dinobase add stripe --api-key sk_test_... && dinobase sync
    python react_agent.py "Which customers have overdue invoices?"
"""

from __future__ import annotations

import sys

from llama_index.core.agent import ReActAgent
from llama_index.llms.anthropic import Anthropic

sys.path.insert(0, "..")
from tool_spec import DinobaseToolSpec


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "What data sources are connected?"

    llm = Anthropic(model="claude-sonnet-4-6")
    tool_spec = DinobaseToolSpec()
    tools = tool_spec.to_tool_list()

    agent = ReActAgent.from_tools(
        tools,
        llm=llm,
        verbose=True,
        system_prompt=(
            "You are a data analyst with access to Dinobase — a SQL database "
            "containing business data synced from multiple SaaS tools.\n\n"
            "Workflow:\n"
            "1. Use dinobase_list_connectors to see what data is available\n"
            "2. Use dinobase_describe on relevant tables to understand schemas\n"
            "3. Use dinobase_query to run SQL (DuckDB dialect, tables are schema.table)\n"
            "4. Present results clearly with your analysis"
        ),
    )

    response = agent.chat(question)
    print(response.response)


if __name__ == "__main__":
    main()
