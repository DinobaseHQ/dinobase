"""Background agent that builds the semantic layer for a synced source.

Runs as a daemon thread after every successful sync. Two tiers:
  1. Heuristic pass — FK relationship detection from column name patterns (no API key needed)
  2. Claude pass   — LLM-generated table/column descriptions (needs ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any

from dinobase.annotations import (
    AnnotationInput,
    RelationshipInput,
    apply_annotation,
    apply_relationship,
)
from dinobase.db import DinobaseDB

# Column name suffixes that suggest a foreign key relationship
_FK_SUFFIXES = ("_id", "__id", "_uuid", "_key", "_fk")

# Mutation keywords to block in the read-only query tool
_MUTATION_KEYWORDS = frozenset(
    ["UPDATE", "INSERT", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "REPLACE"]
)

_AGENT_SYSTEM_PROMPT = """\
You are building the semantic layer for the Dinobase source "{source_name}".

Your job: audit what is already annotated, then fill every gap — table descriptions, \
column docs, PII flags, and relationships. Do not overwrite annotations that already exist.

### Workflow

**Step 1 — Audit gaps** using the query tool:
```
SELECT table_name, row_count FROM _dinobase.tables WHERE schema_name = '{source_name}' AND description IS NULL ORDER BY row_count DESC
SELECT from_table, from_column, to_table, to_column, cardinality FROM _dinobase.relationships WHERE from_schema = '{source_name}' OR to_schema = '{source_name}'
SELECT table_name, column_name, description FROM _dinobase.columns WHERE schema_name = '{source_name}' AND description IS NOT NULL ORDER BY table_name
SELECT table_name, column_name, key, value FROM _dinobase.metadata WHERE schema_name = '{source_name}' ORDER BY table_name, column_name, key
```

**Step 2 — Explore gaps**: for each table missing a description, query its schema and a sample:
```
SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = '{source_name}' AND table_name = '<table>' ORDER BY ordinal_position
SELECT * FROM "{source_name}"."<table>" LIMIT 3
```
Understand: what entity does this table represent? Which columns carry business data vs noise? \
Which are PII? Which are foreign keys?

**Step 3 — Write one combined annotate call** with ALL gaps — mix annotation and relationship \
items in a single call. Do not call annotate multiple times.

**Step 4 — Verify**: query tables still missing descriptions:
```
SELECT table_name FROM _dinobase.tables WHERE schema_name = '{source_name}' AND description IS NULL
```

### Annotation rules
- Every table gets a description, even junction/child tables.
- Skip noisy columns: `*_url`, `node_id`, `_dlt_load_id`, `_dlt_id`, `_dlt_list_idx`.
- Annotate join keys: `_dlt_parent_id` → key="description", value="Join key to <parent>._dlt_id".
- Be specific: "Customer's billing email" not "Email"; "ISO 8601 timestamp, used for incremental sync" not "Updated at".
- Flag all PII with key="pii", value="true": email, name, phone, IP, any user-identifying field.
- Map every relationship you can identify from FK column names and dlt parent-child structure.
- Do not include items that already have correct annotations (from Step 1 audit).
"""

_TOOLS = [
    {
        "name": "query",
        "description": (
            "Execute a read-only SQL query against the database (DuckDB dialect). "
            "Use to inspect _dinobase.tables, _dinobase.columns, _dinobase.relationships, "
            "_dinobase.metadata, information_schema.columns, and sample table data. "
            "Always add LIMIT 3 for sample data queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The SQL query to execute"}
            },
            "required": ["sql"],
        },
    },
    {
        "name": "annotate",
        "description": (
            "Write annotations (table/column descriptions, PII flags) and relationship edges. "
            "Pass a list of annotation items and/or relationship items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {
                                "description": "Annotation item for a table or column",
                                "type": "object",
                                "properties": {
                                    "target": {
                                        "type": "string",
                                        "description": "'schema.table' or 'schema.table.column'",
                                    },
                                    "key": {
                                        "type": "string",
                                        "description": "'description', 'note', 'pii', 'owner', etc.",
                                    },
                                    "value": {"type": "string"},
                                },
                                "required": ["target", "key", "value"],
                            },
                            {
                                "description": "Relationship edge between two tables",
                                "type": "object",
                                "properties": {
                                    "from_table": {"type": "string"},
                                    "from_column": {"type": "string"},
                                    "to_table": {"type": "string"},
                                    "to_column": {"type": "string"},
                                    "cardinality": {
                                        "type": "string",
                                        "enum": ["one_to_one", "one_to_many", "many_to_many"],
                                    },
                                    "description": {"type": "string"},
                                },
                                "required": ["from_table", "from_column", "to_table", "to_column"],
                            },
                        ]
                    },
                }
            },
            "required": ["items"],
        },
    },
]


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------


def is_source_annotated(db: DinobaseDB, source_name: str) -> bool:
    """True if source has at least one relationship AND all tables are described."""
    if not db.has_relationships(source_name):
        return False
    tables = [t for t in db.get_tables(source_name) if not t.startswith("_dlt_")]
    if not tables:
        return True
    return all(db.get_table_description(source_name, t) is not None for t in tables)


# ---------------------------------------------------------------------------
# Heuristic FK detection
# ---------------------------------------------------------------------------


def detect_relationships_heuristic(
    db: DinobaseDB, source_name: str
) -> list[RelationshipInput]:
    """Detect FK relationships from column name patterns (no LLM needed)."""
    tables = set(t for t in db.get_tables(source_name) if not t.startswith("_dlt_"))
    results: list[RelationshipInput] = []
    seen: set[tuple[str, str, str, str]] = set()

    for table in tables:
        cols = db.get_columns(source_name, table)
        for col in cols:
            col_name: str = col["column_name"]
            for suffix in _FK_SUFFIXES:
                if not col_name.endswith(suffix) or col_name == suffix:
                    continue
                stem = col_name[: -len(suffix)]
                for candidate in [stem, stem + "s", stem + "es"]:
                    if candidate not in tables or candidate == table:
                        continue
                    key = (table, col_name, candidate, "id")
                    if key in seen:
                        break
                    seen.add(key)
                    results.append(
                        RelationshipInput(
                            from_table=f"{source_name}.{table}",
                            from_column=col_name,
                            to_table=f"{source_name}.{candidate}",
                            to_column="id",
                            cardinality="one_to_many",
                            description=(
                                f"Heuristic: {table}.{col_name} references {candidate}.id"
                            ),
                        )
                    )
                    break

    return results


# ---------------------------------------------------------------------------
# Claude agent tool dispatch
# ---------------------------------------------------------------------------


def _dispatch_tool(db: DinobaseDB, tool_name: str, tool_input: dict[str, Any]) -> str:
    try:
        if tool_name == "query":
            sql: str = tool_input["sql"]
            first_word = sql.strip().split()[0].upper() if sql.strip() else ""
            if first_word in _MUTATION_KEYWORDS:
                return json.dumps({"error": "Mutations are not allowed in the semantic agent query tool"})
            rows = db.query(sql)
            return json.dumps(rows[:50], default=str)

        if tool_name == "annotate":
            items_raw: list[dict] = tool_input["items"]
            results = []
            for item_dict in items_raw:
                try:
                    if "target" in item_dict:
                        item_ann = AnnotationInput(**item_dict)
                        results.append(apply_annotation(db, item_ann))
                    elif "from_table" in item_dict:
                        item_rel = RelationshipInput(**item_dict)
                        results.append(apply_relationship(db, item_rel))
                    else:
                        results.append({"error": f"Unknown item format: {item_dict}"})
                except Exception as e:
                    results.append({"error": str(e), "item": item_dict})
            return json.dumps(results, default=str)

        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Claude agent loop
# ---------------------------------------------------------------------------


def run_claude_agent(db: DinobaseDB, source_name: str, api_key: str) -> None:
    """Run a Claude agent (Haiku) to generate descriptions and PII flags."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    system = _AGENT_SYSTEM_PROMPT.format(source_name=source_name)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"Build the semantic layer for source: {source_name}"}
    ]

    for _ in range(20):  # hard cap to prevent runaway loops
        response = client.messages.create(
            model=os.environ.get("DINOBASE_SEMANTIC_MODEL", "claude-haiku-4-5"),
            max_tokens=4096,
            system=system,
            tools=_TOOLS,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_str = _dispatch_tool(db, block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    }
                )

        if not tool_results:
            break

        messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class SemanticAgent:
    def __init__(self, db: DinobaseDB, source_name: str) -> None:
        self.db = db
        self.source_name = source_name

    def run(self) -> None:
        """Run heuristic detection + optional Claude agent. Never raises."""
        try:
            self._run_inner()
        except Exception as e:
            print(
                f"[semantic-agent] {self.source_name} failed: {e}",
                file=sys.stderr,
            )

    def _run_inner(self) -> None:
        if is_source_annotated(self.db, self.source_name):
            print(
                f"[semantic-agent] {self.source_name}: already annotated, skipping",
                file=sys.stderr,
            )
            return

        # Tier 1: heuristic FK detection (always runs, no LLM needed)
        relationships = detect_relationships_heuristic(self.db, self.source_name)
        if relationships:
            for rel in relationships:
                apply_relationship(self.db, rel)
            print(
                f"[semantic-agent] {self.source_name}: "
                f"heuristic detected {len(relationships)} relationship(s)",
                file=sys.stderr,
            )

        # Tier 2: built-in Claude agent loop (requires ANTHROPIC_API_KEY)
        #
        # Note on "why not use the Claude Code skill directly":
        # The .claude/skills/indexing-semantic-layer/SKILL.md skill is designed for
        # *interactive* Claude Code sessions where it spawns a native subagent with full
        # tool access. Running it via `claude --print` subprocess doesn't work well here
        # because (a) spawning a subagent in subprocess mode is unreliable and slow,
        # (b) the skill uses `uv run dinobase` which requires a project-dir context,
        # and (c) the `claude` CLI won't be in PATH in cloud containers.
        #
        # The system prompt below IS the skill's logic, translated to direct Anthropic API
        # calls so it works with just ANTHROPIC_API_KEY — no claude CLI required.
        # The skill remains the canonical human-triggered path; this is the daemon path.
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print(
                f"[semantic-agent] {self.source_name}: "
                "no ANTHROPIC_API_KEY, skipping LLM annotation",
                file=sys.stderr,
            )
            return

        try:
            import anthropic as _  # noqa: F401
        except ImportError:
            print(
                "[semantic-agent] 'anthropic' package not installed, skipping LLM annotation "
                "(install with: pip install anthropic)",
                file=sys.stderr,
            )
            return

        print(
            f"[semantic-agent] {self.source_name}: running Claude annotation...",
            file=sys.stderr,
        )
        run_claude_agent(self.db, self.source_name, api_key)
        print(
            f"[semantic-agent] {self.source_name}: annotation complete",
            file=sys.stderr,
        )

        if self.db.is_cloud:
            self.db.save_cloud_metadata()


# ---------------------------------------------------------------------------
# Public entry point — spawn a daemon thread
# ---------------------------------------------------------------------------


def spawn_semantic_agent(source_name: str) -> None:
    """Spawn the SemanticAgent in a daemon background thread.

    Called after a successful sync. Creates a fresh DinobaseDB instance
    (auto-detects local vs cloud from environment variables) so the thread
    owns its own connection lifecycle independently of the caller's DB handle.

    Skips immediately if DINOBASE_AUTO_ANNOTATE=false.
    """
    from dinobase.config import is_auto_annotate_enabled

    if not is_auto_annotate_enabled():
        return

    def _run() -> None:
        db = DinobaseDB()
        try:
            SemanticAgent(db, source_name).run()
        except Exception as e:
            print(
                f"[semantic-agent] thread error for {source_name}: {e}",
                file=sys.stderr,
            )
        finally:
            try:
                db.close()
            except Exception:
                pass

    t = threading.Thread(
        target=_run,
        daemon=True,
        name=f"dinobase-semantic-{source_name}",
    )
    t.start()
