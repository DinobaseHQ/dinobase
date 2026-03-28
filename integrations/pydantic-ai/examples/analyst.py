"""Example: Pydantic AI data analyst agent powered by Dinobase.

Run:
    pip install pydantic-ai dinobase
    export ANTHROPIC_API_KEY=sk-ant-...
    dinobase init && dinobase add stripe --api-key sk_test_... && dinobase sync
    python analyst.py "Which customers have overdue invoices?"
"""

from __future__ import annotations

import sys

sys.path.insert(0, "..")
from tools import DinobaseDeps, dinobase_agent


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "What data sources are connected?"

    result = dinobase_agent.run_sync(question, deps=DinobaseDeps())

    print(result.output)


if __name__ == "__main__":
    main()
