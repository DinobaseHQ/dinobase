"""Example: CrewAI data analyst crew powered by Dinobase.

Run:
    pip install crewai dinobase
    dinobase init && dinobase add stripe --api-key sk_test_... && dinobase sync
    python data_analyst_crew.py "Which customers have overdue invoices?"
"""

from __future__ import annotations

import sys

from crewai import Agent, Crew, Process, Task

# Import Dinobase tools
sys.path.insert(0, "..")
from tools import dinobase_query, dinobase_list_connectors, dinobase_describe


def create_crew(question: str) -> Crew:
    data_analyst = Agent(
        role="Data Analyst",
        goal="Answer business questions by querying Dinobase with SQL",
        backstory=(
            "You are a skilled data analyst who queries business data across "
            "multiple SaaS tools (CRM, billing, support, etc.) using SQL. "
            "You always check what data is available before writing queries, "
            "and you use describe to understand table schemas."
        ),
        tools=[dinobase_list_connectors, dinobase_describe, dinobase_query],
        verbose=True,
    )

    analyze_task = Task(
        description=(
            f"Answer this business question: {question}\n\n"
            "Steps:\n"
            "1. Use dinobase_list_connectors to see what data is available\n"
            "2. Use dinobase_describe on relevant tables to understand columns\n"
            "3. Write and execute SQL queries with dinobase_query\n"
            "4. Present the results clearly with your analysis"
        ),
        expected_output="A clear answer to the question with supporting data and SQL used.",
        agent=data_analyst,
    )

    return Crew(
        agents=[data_analyst],
        tasks=[analyze_task],
        process=Process.sequential,
        verbose=True,
    )


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "What data sources are connected?"
    crew = create_crew(question)
    result = crew.kickoff()
    print("\n" + "=" * 60)
    print("RESULT:")
    print("=" * 60)
    print(result)
