# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Sandbox — side-by-side comparison of Dinobase SQL vs per-source MCP tools.

Streams SSE events as two LLM agents work on the same question concurrently:
one using Dinobase (single SQL interface) and one using simulated per-source
MCP tools (one paginated list endpoint per table, no cross-source joins).

After both finish, a judge model scores each answer for correctness.

Requires: ANTHROPIC_API_KEY env var.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dinobase_hosted.auth import User, get_current_user


def _get_seed_engine():
    """Create a QueryEngine pointing at the shared sandbox seed database.

    Requires DINOBASE_SEED_STORAGE_URL to be set (populated by scripts/seed_s3.py).
    The seed database is read-only and shared across all sandbox users.
    """
    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    seed_url = os.environ.get("DINOBASE_SEED_STORAGE_URL")
    if not seed_url:
        raise HTTPException(
            503,
            "Sandbox is not configured. Set DINOBASE_SEED_STORAGE_URL on the server.",
        )
    db = DinobaseDB(storage_url=seed_url)
    return QueryEngine(db), db

router = APIRouter(tags=["sandbox"])

MAX_TURNS = 10
MAX_OUTPUT_TOKENS = 4096
JUDGE_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

ALLOWED_MODELS = {
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
}

JUDGE_SYSTEM = """You are a benchmark evaluation judge. Determine whether an agent's response correctly answers the question.

Scoring rules:
- "correct": the agent's answer contains the right information. Minor rounding (±5%) is OK. Formatting doesn't matter.
- "partial": right approach but the final answer is materially wrong (>10% off for numbers, missing key items for lists).
- Neither correct nor partial: wrong, incomplete, or the agent failed to answer.

For dollar amounts: order of magnitude MUST be correct — 100x off (e.g. cents vs dollars) is WRONG, not partial.
If no expected answer is provided, score whether the agent gave a complete and reasonable answer to the question.

Respond with ONLY a JSON object: {"correct": true/false, "partial": true/false, "explanation": "one sentence"}"""

# Tool definitions — identical to the real MCP server
DINOBASE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_sources",
        "description": "List all connected data sources with their tables, row counts, and last sync time.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "describe",
        "description": "Describe a table's columns, types, annotations, and sample rows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Table to describe, e.g. 'stripe.charges' or 'hubspot.deals'",
                }
            },
            "required": ["table"],
        },
    },
    {
        "name": "query",
        "description": (
            "Execute a SQL query against the database. "
            "Use `describe` first to understand columns and types. "
            "Reference tables as schema.table (e.g. hubspot.deals, stripe.charges)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL query (DuckDB dialect).",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Maximum rows to return (default 200).",
                    "default": 200,
                },
            },
            "required": ["sql"],
        },
    },
]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SandboxRunRequest(BaseModel):
    question: str
    model: str = DEFAULT_MODEL
    expected_answer: str | None = None


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------

def _get_source_tables(engine) -> list[tuple[str, str]]:
    """Return (schema, table) pairs from engine.list_sources()."""
    result = engine.list_sources()
    pairs: list[tuple[str, str]] = []
    for source in result.get("sources", []):
        schema = source["name"]
        for table_info in source.get("tables", []):
            pairs.append((schema, table_info["name"]))
    return pairs


# ---------------------------------------------------------------------------
# Per-source MCP tool builders
# ---------------------------------------------------------------------------

def _make_mcp_tools(source_tables: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """One paginated list tool per source table, simulating separate API endpoints."""
    tools = []
    for schema, table in source_tables:
        tools.append({
            "name": f"{schema}_list_{table}",
            "description": (
                f"Fetch {table} records from the {schema} API. "
                f"Returns up to 100 records per page as JSON."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max results per page (default 100, max 100).",
                        "default": 100,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset. Use next_offset from previous response.",
                        "default": 0,
                    },
                },
                "required": [],
            },
        })
    return tools


def _make_mcp_system(source_tables: list[tuple[str, str]]) -> str:
    source_names = sorted({schema for schema, _ in source_tables})
    names = " and ".join(source_names) if source_names else "your data sources"
    return (
        f"You are a data analyst with access to {names} API tools.\n\n"
        f"Use these tools to answer business questions. Each tool returns records from a single API endpoint.\n\n"
        f"Note: These are separate systems with separate APIs. There is no built-in way to join or aggregate "
        f"data across sources. If you need to correlate records across sources, fetch from each and match "
        f"manually (e.g. by email address or customer ID)."
    )


# ---------------------------------------------------------------------------
# Tool handlers (synchronous — called via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _handle_dinobase_tool(engine, name: str, tool_input: dict) -> str:
    """Execute a Dinobase tool and return JSON string result."""
    if name == "list_sources":
        return json.dumps(engine.list_sources(), default=str)
    if name == "describe":
        table = tool_input.get("table", "")
        if not table:
            return json.dumps({"error": "Missing required parameter: table"})
        return json.dumps(engine.describe_table(table), default=str)
    if name == "query":
        sql = tool_input.get("sql", "")
        if not sql:
            return json.dumps({"error": "Missing required parameter: sql"})
        return json.dumps(
            engine.execute(sql, max_rows=tool_input.get("max_rows", 200)),
            default=str,
        )
    return json.dumps({"error": f"Unknown tool: {name}"})


def _handle_mcp_tool(
    engine,
    name: str,
    tool_input: dict,
    source_tables: list[tuple[str, str]],
) -> str:
    """Execute a per-source MCP tool — paginated JSON from one table."""
    limit = min(int(tool_input.get("limit", 100)), 100)
    offset = int(tool_input.get("offset", 0))

    for schema, table in source_tables:
        if name == f"{schema}_list_{table}":
            count_result = engine.execute(
                f"SELECT COUNT(*) AS n FROM {schema}.{table}", max_rows=1
            )
            total = (
                count_result["rows"][0]["n"]
                if count_result.get("rows")
                else 0
            )

            page_result = engine.execute(
                f"SELECT * FROM {schema}.{table} LIMIT {limit} OFFSET {offset}",
                max_rows=limit,
            )
            data = page_result.get("rows", [])
            has_more = (offset + limit) < total
            response: dict[str, Any] = {
                "data": data,
                "count": len(data),
                "total_count": total,
                "has_more": has_more,
            }
            if has_more:
                response["next_offset"] = offset + limit
            return json.dumps(response, default=str)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ---------------------------------------------------------------------------
# Suggested questions
# ---------------------------------------------------------------------------

def _suggest_questions(source_tables: list[tuple[str, str]]) -> list[str]:
    """Generate example questions based on the user's connected sources."""
    questions: list[str] = ["Give me a summary of all my connected data sources."]
    seen_schemas: set[str] = set()

    for schema, table in source_tables:
        if schema not in seen_schemas:
            seen_schemas.add(schema)
            questions.append(f"How many records are in {schema}.{table}?")
        else:
            questions.append(f"Show me the top 10 rows from {schema}.{table}.")

    schemas = sorted(seen_schemas)
    if len(schemas) >= 2:
        questions.append(
            f"Find records that appear in both {schemas[0]} and {schemas[1]} "
            f"(e.g. by matching email or ID)."
        )

    return questions[:8]


# ---------------------------------------------------------------------------
# Agentic loop for one approach
# ---------------------------------------------------------------------------

async def _run_approach(
    approach: str,
    question: str,
    engine,
    source_tables: list[tuple[str, str]],
    model: str,
    queue: asyncio.Queue,
    answers: dict[str, str],
    pending: dict[str, int],
) -> None:
    """Run one approach (dinobase or mcp), pushing SSE events into the queue."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if approach == "dinobase":
        from dinobase.mcp.server import _build_instructions
        system = await asyncio.to_thread(_build_instructions, engine)
        tools = DINOBASE_TOOLS
    else:
        system = _make_mcp_system(source_tables)
        tools = _make_mcp_tools(source_tables)

    messages: list[Any] = [{"role": "user", "content": question}]
    total_in = total_out = tool_calls = turns = 0
    start = time.monotonic()
    answer = "[MAX TURNS REACHED]"

    try:
        for _ in range(MAX_TURNS):
            turns += 1

            resp = await client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                tools=tools,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )

            total_in += resp.usage.input_tokens
            total_out += resp.usage.output_tokens

            text_parts = [b.text for b in resp.content if b.type == "text"]
            tool_use_blocks = [b for b in resp.content if b.type == "tool_use"]

            if text_parts:
                await queue.put({
                    "type": "turn",
                    "approach": approach,
                    "role": "assistant",
                    "text": "\n".join(text_parts),
                })

            if resp.stop_reason == "end_turn":
                answer = "\n".join(text_parts)
                break

            # Append assistant message with content blocks
            messages.append({"role": "assistant", "content": resp.content})  # type: ignore[arg-type]

            tool_result_content: list[dict] = []
            for block in tool_use_blocks:
                tool_calls += 1
                tool_input = dict(block.input) if block.input else {}

                await queue.put({
                    "type": "turn",
                    "approach": approach,
                    "role": "tool",
                    "tool": block.name,
                    "input": tool_input,
                })

                # Execute tool in thread pool — DuckDB is synchronous
                if approach == "dinobase":
                    result = await asyncio.to_thread(
                        _handle_dinobase_tool, engine, block.name, tool_input
                    )
                else:
                    result = await asyncio.to_thread(
                        _handle_mcp_tool, engine, block.name, tool_input, source_tables
                    )

                preview = result[:1200] + "…" if len(result) > 1200 else result
                await queue.put({
                    "type": "turn",
                    "approach": approach,
                    "role": "tool_result",
                    "tool": block.name,
                    "output": preview,
                })

                tool_result_content.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            if not tool_use_blocks and not text_parts:
                break

            if tool_result_content:
                messages.append({"role": "user", "content": tool_result_content})

    except Exception as exc:
        await queue.put({
            "type": "error",
            "approach": approach,
            "message": str(exc),
        })
        answer = f"[ERROR: {exc}]"

    answers[approach] = answer
    await queue.put({
        "type": "metric",
        "approach": approach,
        "tokens_in": total_in,
        "tokens_out": total_out,
        "latency_ms": int((time.monotonic() - start) * 1000),
        "tool_calls": tool_calls,
        "turns": turns,
    })

    # Decrement counter; put sentinel when both approaches are done
    pending["count"] -= 1
    if pending["count"] == 0:
        await queue.put(None)


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

async def _judge_answer(
    client,
    question: str,
    answer: str,
    expected_answer: str | None,
) -> dict[str, Any]:
    """Score one answer using the Haiku judge model."""
    if expected_answer:
        prompt = (
            f"Question: {question}\n\n"
            f"Expected answer: {expected_answer}\n\n"
            f"Agent response:\n{answer}\n\n"
            f"Is the agent's answer correct?"
        )
    else:
        prompt = (
            f"Question: {question}\n\n"
            f"Agent response:\n{answer}\n\n"
            f"Did the agent give a complete and reasonable answer?"
        )

    try:
        resp = await client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=256,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip() if resp.content else "{}"
        # Strip markdown code fences if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as exc:
        return {
            "correct": False,
            "partial": False,
            "explanation": f"Judge error: {exc}",
        }


# ---------------------------------------------------------------------------
# SSE event generator
# ---------------------------------------------------------------------------

async def _stream_events(
    question: str,
    model: str,
    expected_answer: str | None,
    engine_dino,
    engine_mcp,
    source_tables: list[tuple[str, str]],
) -> AsyncGenerator[str, None]:
    """Yield SSE-encoded data lines for both approaches running concurrently."""
    import anthropic

    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    answers: dict[str, str] = {}
    pending = {"count": 2}

    asyncio.create_task(
        _run_approach("dinobase", question, engine_dino, source_tables, model, queue, answers, pending)
    )
    asyncio.create_task(
        _run_approach("mcp", question, engine_mcp, source_tables, model, queue, answers, pending)
    )

    # Drain events until sentinel (None)
    while True:
        event = await queue.get()
        if event is None:
            break
        yield f"data: {json.dumps(event)}\n\n"

    # Judge both answers
    judge_client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    for approach in ("dinobase", "mcp"):
        score = await _judge_answer(
            judge_client, question, answers.get(approach, ""), expected_answer
        )
        yield f"data: {json.dumps({'type': 'score', 'approach': approach, **score})}\n\n"

    yield 'data: {"type":"done"}\n\n'


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def get_sandbox_info(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return connected sources, suggested questions, and available models."""
    engine, db = _get_seed_engine()
    try:
        source_tables = _get_source_tables(engine)
        sources_info = engine.list_sources()
        return {
            "sources": sources_info.get("sources", []),
            "suggested_questions": _suggest_questions(source_tables),
            "models": sorted(ALLOWED_MODELS),
            "default_model": DEFAULT_MODEL,
        }
    finally:
        db.close()


@router.post("/run")
async def run_sandbox(
    body: SandboxRunRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream a side-by-side Dinobase vs MCP comparison as SSE events."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            503,
            "Sandbox requires ANTHROPIC_API_KEY to be configured on the server.",
        )

    if body.model not in ALLOWED_MODELS:
        raise HTTPException(
            400,
            f"Model must be one of: {', '.join(sorted(ALLOWED_MODELS))}",
        )

    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Question cannot be empty.")

    # Two separate engines so concurrent DuckDB calls don't share a connection
    engine_dino, db_dino = _get_seed_engine()
    engine_mcp, db_mcp = _get_seed_engine()

    source_tables = _get_source_tables(engine_dino)
    if not source_tables:
        db_dino.close()
        db_mcp.close()
        raise HTTPException(500, "Sandbox seed database is empty.")

    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for chunk in _stream_events(
                question,
                body.model,
                body.expected_answer,
                engine_dino,
                engine_mcp,
                source_tables,
            ):
                yield chunk
        finally:
            db_dino.close()
            db_mcp.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
