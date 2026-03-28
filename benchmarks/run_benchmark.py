#!/usr/bin/env python3
"""
Dinobase Benchmark: SQL vs Per-Source MCP Tools

Multi-model, multi-vertical benchmark comparing:
  1. Dinobase (SQL) — agent gets list_sources, describe, query tools
  2. Raw MCP tools  — agent gets per-source tools returning paginated JSON

Supports 10+ models via OpenRouter, multiple verticals, N runs per question,
deterministic + LLM-judge scoring, budget guards, and statistical reporting.

Usage:
    python benchmarks/run_benchmark.py                                       # sonnet, revops, N=3
    python benchmarks/run_benchmark.py --models claude-sonnet-4.6,o4-mini    # specific models
    python benchmarks/run_benchmark.py --models all                          # all models
    python benchmarks/run_benchmark.py --vertical ecommerce                  # specific vertical
    python benchmarks/run_benchmark.py --vertical all                        # all verticals
    python benchmarks/run_benchmark.py --runs 5 --budget 20                  # 5 runs, $20 cap
    python benchmarks/run_benchmark.py --dry-run                             # cost estimate
    python benchmarks/run_benchmark.py --resume                              # resume progress
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BENCHMARKS_DIR = Path(__file__).parent
PROJECT_ROOT = BENCHMARKS_DIR.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
RESULTS_DIR = BENCHMARKS_DIR / "results"
QUESTIONS_FILE = BENCHMARKS_DIR / "questions.json"

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MAX_TURNS = 15
MAX_TOKENS = 4096
DEFAULT_BUDGET = 25.0
DEFAULT_RUNS = 3
DEFAULT_JUDGE = "anthropic/claude-haiku-4.5"

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    model_id: str
    display_name: str
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0


# Fallback model list — pricing is fetched live from OpenRouter when possible
MODELS: dict[str, ModelConfig] = {
    # Small / cheap
    "qwen-3.5-27b": ModelConfig("qwen/qwen3.5-27b", "Qwen 3.5 27B", 0.20, 1.56),
    "minimax-m2.7": ModelConfig("minimax/minimax-m2.7", "MiniMax M2.7", 0.30, 1.20),
    "gemini-3-flash": ModelConfig("google/gemini-3-flash-preview", "Gemini 3 Flash", 0.50, 3.00),
    "claude-haiku-4.5": ModelConfig("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", 1.00, 5.00),
    "glm-5-turbo": ModelConfig("z-ai/glm-5-turbo", "GLM-5 Turbo", 1.20, 4.00),
    # Mid / frontier
    "deepseek-v3.2": ModelConfig("deepseek/deepseek-v3.2", "DeepSeek V3.2", 0.26, 0.38),
    "kimi-k2.5": ModelConfig("moonshotai/kimi-k2.5", "Kimi K2.5", 0.45, 2.20),
    "gpt-5.4": ModelConfig("openai/gpt-5.4", "GPT-5.4", 2.50, 15.00),
    "gemini-3.1-pro": ModelConfig("google/gemini-3.1-pro-preview", "Gemini 3.1 Pro", 2.00, 12.00),
    # Large / expensive
    "claude-sonnet-4.6": ModelConfig("anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6", 3.00, 15.00),
    "claude-opus-4.6": ModelConfig("anthropic/claude-opus-4.6", "Claude Opus 4.6", 5.00, 25.00),
}




def compute_cost(input_tokens: int, output_tokens: int, config: ModelConfig) -> float:
    return (input_tokens * config.cost_per_1m_input / 1_000_000
            + output_tokens * config.cost_per_1m_output / 1_000_000)


# ---------------------------------------------------------------------------
# OpenRouter API client
# ---------------------------------------------------------------------------

def call_openrouter(
    api_key: str,
    model_id: str,
    system: str,
    tools: list[dict],
    messages: list[dict],
    temperature: float = 0.0,
) -> dict:
    """Call OpenRouter with OpenAI-compatible tool-use format.

    Returns: {content, stop_reason, input_tokens, output_tokens, latency_ms}
    """
    # Convert tools to OpenAI format
    oai_tools = []
    for t in tools:
        oai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })

    # Convert messages to OpenAI format
    oai_messages = [{"role": "system", "content": system}]
    for msg in messages:
        if msg["role"] == "user":
            if isinstance(msg["content"], str):
                oai_messages.append({"role": "user", "content": msg["content"]})
            elif isinstance(msg["content"], list):
                # Tool results
                for item in msg["content"]:
                    if item.get("type") == "tool_result":
                        oai_messages.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": item["content"],
                        })
        elif msg["role"] == "assistant":
            content = msg["content"]
            if isinstance(content, list):
                # Convert Anthropic content blocks to OpenAI format
                text_parts = []
                tool_calls = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"]),
                                },
                            })
                    else:
                        # Could be an Anthropic content block object
                        if hasattr(block, "type"):
                            if block.type == "text":
                                text_parts.append(block.text)
                            elif block.type == "tool_use":
                                tool_calls.append({
                                    "id": block.id,
                                    "type": "function",
                                    "function": {
                                        "name": block.name,
                                        "arguments": json.dumps(block.input),
                                    },
                                })
                assistant_msg = {"role": "assistant"}
                if text_parts:
                    assistant_msg["content"] = "\n".join(text_parts)
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                    if "content" not in assistant_msg:
                        assistant_msg["content"] = ""
                oai_messages.append(assistant_msg)
            elif isinstance(content, str):
                oai_messages.append({"role": "assistant", "content": content})

    start = time.time()

    # Retry loop
    for attempt in range(8):
        try:
            resp = httpx.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": oai_messages,
                    "tools": oai_tools if oai_tools else None,
                    "temperature": temperature,
                    "max_tokens": MAX_TOKENS,
                    "seed": 42,
                },
                timeout=120,
            )
            if resp.status_code == 429:
                wait = 60
                print(f"         Rate limited (attempt {attempt+1}/8). Waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = min(2 ** attempt + 1, 30)
                print(f"         Server error {resp.status_code} (attempt {attempt+1}/8). Retrying in {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code in (400, 401, 402, 403):
                body = resp.text[:300]
                if attempt == 0:
                    print(f"         {resp.status_code} error: {body}")
                # Non-retryable errors — don't waste time retrying
                resp.raise_for_status()
            break
        except httpx.TimeoutException:
            wait = min(2 ** attempt + 1, 30)
            print(f"         Timeout (attempt {attempt+1}/8). Retrying in {wait}s...")
            time.sleep(wait)
            continue
        except httpx.HTTPStatusError as e:
            if attempt == 7:
                raise
            wait = min(2 ** attempt + 1, 30)
            print(f"         HTTP error (attempt {attempt+1}/8): {e}. Retrying in {wait}s...")
            time.sleep(wait)
            continue

    latency_ms = int((time.time() - start) * 1000)
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"OpenRouter error: {data['error']}")

    choice = data["choices"][0]
    message = choice["message"]
    usage = data.get("usage", {})

    # Convert response back to unified format
    content = []
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    if message.get("tool_calls"):
        for tc in message["tool_calls"]:
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["function"]["name"],
                "input": args,
            })

    stop_reason = "end_turn"
    if message.get("tool_calls"):
        stop_reason = "tool_use"
    elif choice.get("finish_reason") == "length":
        stop_reason = "max_tokens"

    return {
        "content": content,
        "stop_reason": stop_reason,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# Schema definitions per vertical
# ---------------------------------------------------------------------------

VERTICAL_SCHEMAS = {
    "revops": {
        "stripe": ["customers", "subscriptions", "charges", "invoices"],
        "hubspot": ["contacts", "companies", "deals"],
    },
    "ecommerce": {
        "shopify": ["products", "customers", "orders"],
        "stripe_ecom": ["customers", "charges"],
    },
    "knowledge_base": {
        "notion": ["databases", "pages"],
        "github": ["repos", "issues"],
        "slack": ["channels", "messages"],
    },
    "devops": {
        "github": ["pull_requests", "deployments"],
        "pagerduty": ["services", "incidents"],
        "datadog": ["monitors"],
    },
    "customer_support": {
        "zendesk": ["agents", "tickets"],
        "analytics": ["events"],
        "stripe_support": ["customers", "subscriptions"],
    },
}

# Sources that have Stripe OpenAPI metadata available
STRIPE_SCHEMAS = {"stripe", "stripe_ecom", "stripe_support"}


# ---------------------------------------------------------------------------
# Dinobase setup — uses the REAL product (DinobaseDB + QueryEngine)
# ---------------------------------------------------------------------------

def setup_dinobase(verticals: list[str] | None = None) -> "QueryEngine":
    """Set up a real Dinobase instance with sample data, simulating a real sync.

    This uses the actual product code paths:
    - DinobaseDB for storage + metadata
    - Parquet loading simulating dlt sync output
    - Stripe OpenAPI metadata extraction for annotations
    - Sync logging so freshness tracking works
    - QueryEngine for query execution, describe, list_sources
    """
    import tempfile
    os.environ.setdefault("DINOBASE_DIR", tempfile.mkdtemp())

    from dinobase.db import DinobaseDB
    from dinobase.query.engine import QueryEngine

    tmp = Path(os.environ["DINOBASE_DIR"])
    db = DinobaseDB(tmp / "benchmark.duckdb")

    if verticals is None:
        verticals = list(VERTICAL_SCHEMAS.keys())

    created_schemas = set()
    for v in verticals:
        for schema, tables in VERTICAL_SCHEMAS.get(v, {}).items():
            if schema in created_schemas:
                continue
            created_schemas.add(schema)

            # Create schema and load parquet files (simulating dlt sync output)
            db.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            loaded_tables = []
            total_rows = 0
            for table in tables:
                path = SAMPLE_DATA_DIR / f"{schema}_{table}.parquet"
                if path.exists():
                    db.conn.execute(f"DROP TABLE IF EXISTS {schema}.{table}")
                    db.conn.execute(
                        f"CREATE TABLE {schema}.{table} AS "
                        f"SELECT * FROM read_parquet('{path}')"
                    )
                    rows = db.conn.execute(f"SELECT COUNT(*) FROM {schema}.{table}").fetchone()[0]
                    loaded_tables.append(table)
                    total_rows += rows

            # Extract real metadata from Stripe OpenAPI spec (like a real sync does)
            annotations = None
            if schema in STRIPE_SCHEMAS and loaded_tables:
                try:
                    from dinobase.sync.metadata import extract_stripe_metadata
                    annotations = extract_stripe_metadata("", loaded_tables)
                except Exception as e:
                    print(f"  Warning: Could not extract Stripe metadata for {schema}: {e}")

            # Log the sync (so freshness tracking works)
            sync_id = db.log_sync_start(schema, schema)
            db.log_sync_end(sync_id, "success", tables_synced=len(loaded_tables), rows_synced=total_rows)
            db.update_table_metadata(schema, schema, annotations=annotations)

    return QueryEngine(db)


def make_dinobase_system(engine: "QueryEngine") -> str:
    """Build system prompt using the REAL product's instruction builder."""
    from dinobase.mcp.server import _build_instructions
    return _build_instructions(engine)


# Tool definitions match the real MCP server exactly
DINOBASE_TOOLS = [
    {
        "name": "list_sources",
        "description": "List all connected data sources with their tables, row counts, and last sync time.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "describe",
        "description": "Describe a table's columns, types, annotations, and sample rows. Annotations include data format notes (e.g. 'amounts in cents') and join key hints.",
        "input_schema": {
            "type": "object",
            "properties": {"table": {"type": "string", "description": "Table to describe, e.g. 'stripe.charges' or 'zendesk.tickets'"}},
            "required": ["table"],
        },
    },
    {
        "name": "query",
        "description": "Execute a SQL query against the database. Use `describe` first to understand table columns and data types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL query to execute (DuckDB dialect). Reference tables as schema.table."},
                "max_rows": {"type": "integer", "description": "Maximum rows to return", "default": 200},
            },
            "required": ["sql"],
        },
    },
]


def handle_dinobase_tool(engine: "QueryEngine", name: str, input: dict) -> str:
    """Route tool calls through the REAL QueryEngine — same code path as the MCP server."""
    if name == "list_sources":
        result = engine.list_sources()
        return json.dumps(result, indent=2, default=str)

    elif name == "describe":
        table = input.get("table")
        if not table:
            return json.dumps({"error": "Missing required parameter: table"})
        result = engine.describe_table(table)
        return json.dumps(result, indent=2, default=str)

    elif name == "query":
        sql = input.get("sql")
        if not sql:
            return json.dumps({"error": "Missing required parameter: sql"})
        result = engine.execute(sql, max_rows=input.get("max_rows", 200))
        return json.dumps(result, indent=2, default=str)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ---------------------------------------------------------------------------
# Raw MCP setup — in-memory data served as API-style JSON (no database)
# ---------------------------------------------------------------------------

def load_raw_api_data(verticals: list[str] | None = None) -> dict[str, dict[str, list[dict]]]:
    """Load parquet files into plain Python dicts, simulating API data stores.

    Returns: {schema: {table: [row_dicts]}}
    No database involved — this is what per-source MCP tools would have behind them.
    """
    import pyarrow.parquet as pq

    if verticals is None:
        verticals = list(VERTICAL_SCHEMAS.keys())

    data: dict[str, dict[str, list[dict]]] = {}
    for v in verticals:
        for schema, tables in VERTICAL_SCHEMAS.get(v, {}).items():
            if schema not in data:
                data[schema] = {}
            for table in tables:
                path = SAMPLE_DATA_DIR / f"{schema}_{table}.parquet"
                if path.exists():
                    df = pq.read_table(path).to_pandas()
                    # Convert to plain dicts (like an API would return)
                    records = json.loads(df.to_json(orient="records"))
                    data[schema][table] = records
    return data


def make_raw_mcp_system(vertical: str) -> str:
    source_names = list(VERTICAL_SCHEMAS.get(vertical, {}).keys())
    return f"""You are a data analyst with access to {' and '.join(source_names)} API tools.

Use these tools to answer business questions. Each tool returns records from a single API endpoint.

Note: These are separate systems with separate APIs. There is no built-in way to join or aggregate data across them. If you need to correlate records across sources, you will need to fetch from each and match them manually (e.g., by email address)."""


def make_raw_mcp_tools(vertical: str) -> list[dict]:
    """Generate per-source API tools for a vertical."""
    tools = []
    for schema, tables in VERTICAL_SCHEMAS.get(vertical, {}).items():
        for table in tables:
            tool_name = f"{schema}_list_{table}"
            tools.append({
                "name": tool_name,
                "description": f"Fetch {table} from the {schema} API. Returns up to 100 records per page as JSON.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max results per page (default 100, max 100)", "default": 100},
                        "offset": {"type": "integer", "description": "Pagination offset. Use next_offset from previous response.", "default": 0},
                    },
                    "required": [],
                },
            })
    return tools


def handle_raw_mcp_tool(api_data: dict, name: str, input: dict, vertical: str) -> str:
    """Serve API-style paginated JSON from in-memory data. No database involved."""
    limit = min(input.get("limit", 100), 100)
    offset = input.get("offset", 0)

    # Find the matching source/table from the tool name
    for schema, tables in VERTICAL_SCHEMAS.get(vertical, {}).items():
        for table in tables:
            if name == f"{schema}_list_{table}":
                all_records = api_data.get(schema, {}).get(table, [])
                page = all_records[offset:offset + limit]
                has_more = (offset + len(page)) < len(all_records)
                result = {
                    "data": page,
                    "count": len(page),
                    "total_count": len(all_records),
                    "has_more": has_more,
                }
                if has_more:
                    result["next_offset"] = offset + len(page)
                return json.dumps(result, default=str)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ---------------------------------------------------------------------------
# Ground truth verification (separate plain DuckDB for running SQL checks)
# ---------------------------------------------------------------------------

def setup_ground_truth_db(verticals: list[str] | None = None) -> duckdb.DuckDBPyConnection:
    """Plain DuckDB connection for verifying ground truth SQL. Not used during benchmark."""
    conn = duckdb.connect(":memory:")
    if verticals is None:
        verticals = list(VERTICAL_SCHEMAS.keys())

    for v in verticals:
        for schema, tables in VERTICAL_SCHEMAS.get(v, {}).items():
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            for table in tables:
                path = SAMPLE_DATA_DIR / f"{schema}_{table}.parquet"
                if path.exists():
                    conn.execute(f"DROP TABLE IF EXISTS {schema}.{table}")
                    conn.execute(f"CREATE TABLE {schema}.{table} AS SELECT * FROM read_parquet('{path}')")
    return conn


# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------

def run_question(
    api_key: str,
    engine: "QueryEngine",
    api_data: dict,
    question: str,
    approach: str,
    vertical: str,
    model_config: ModelConfig,
) -> dict:
    if approach == "dinobase":
        system = make_dinobase_system(engine)
        tools = DINOBASE_TOOLS
        handler = lambda n, i: handle_dinobase_tool(engine, n, i)
    else:
        system = make_raw_mcp_system(vertical)
        tools = make_raw_mcp_tools(vertical)
        handler = lambda n, i: handle_raw_mcp_tool(api_data, n, i, vertical)

    messages = [{"role": "user", "content": question}]
    total_input = 0
    total_output = 0
    tool_call_count = 0
    turns = 0
    consecutive_tool_failures = 0
    start = time.time()

    # Conversation trace for debugging
    trace = []
    trace.append({"role": "system", "content": system})
    trace.append({"role": "user", "content": question})

    for _ in range(MAX_TURNS):
        turns += 1

        try:
            resp = call_openrouter(api_key, model_config.model_id, system, tools, messages)
        except Exception as e:
            trace.append({"role": "error", "content": str(e)})
            return {
                "answer": f"[API ERROR: {e}]",
                "total_input_tokens": total_input, "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "tool_calls": tool_call_count, "turns": turns,
                "latency_ms": int((time.time() - start) * 1000),
                "error": str(e), "trace": trace,
            }

        total_input += resp["input_tokens"]
        total_output += resp["output_tokens"]

        if resp["stop_reason"] == "end_turn":
            answer_parts = [b["text"] for b in resp["content"] if b.get("type") == "text"]
            answer = "\n".join(answer_parts)
            trace.append({"role": "assistant", "content": answer})
            return {
                "answer": answer,
                "total_input_tokens": total_input, "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "tool_calls": tool_call_count, "turns": turns,
                "latency_ms": int((time.time() - start) * 1000),
                "trace": trace,
            }

        # Process tool calls
        content = resp["content"]
        messages.append({"role": "assistant", "content": content})

        tool_results = []
        has_tool_use = False
        for block in content:
            if block.get("type") == "tool_use":
                has_tool_use = True
                tool_call_count += 1
                result = handler(block["name"], block["input"])
                # Log the tool call and result (truncate large results for readability)
                result_preview = result[:2000] + "..." if len(result) > 2000 else result
                trace.append({
                    "role": "tool_call", "tool": block["name"],
                    "input": block["input"], "output": result_preview,
                    "output_full_length": len(result),
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result,
                })

        if not has_tool_use:
            consecutive_tool_failures += 1
            if consecutive_tool_failures >= 3:
                trace.append({"role": "error", "content": "3 consecutive turns without tool calls"})
                return {
                    "answer": "[TOOL USE FAILURE: model failed to produce tool calls]",
                    "total_input_tokens": total_input, "total_output_tokens": total_output,
                    "total_tokens": total_input + total_output,
                    "tool_calls": tool_call_count, "turns": turns,
                    "latency_ms": int((time.time() - start) * 1000),
                    "error": "tool_use_failure", "trace": trace,
                }
            # Try to extract text answer
            text_parts = [b["text"] for b in content if b.get("type") == "text"]
            if text_parts:
                answer = "\n".join(text_parts)
                trace.append({"role": "assistant", "content": answer})
                return {
                    "answer": answer,
                    "total_input_tokens": total_input, "total_output_tokens": total_output,
                    "total_tokens": total_input + total_output,
                    "tool_calls": tool_call_count, "turns": turns,
                    "latency_ms": int((time.time() - start) * 1000),
                    "trace": trace,
                }
        else:
            consecutive_tool_failures = 0

        messages.append({"role": "user", "content": tool_results})

    trace.append({"role": "error", "content": f"Max turns ({MAX_TURNS}) reached"})
    return {
        "answer": "[MAX TURNS REACHED]",
        "total_input_tokens": total_input, "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "tool_calls": tool_call_count, "turns": turns,
        "latency_ms": int((time.time() - start) * 1000),
        "trace": trace,
    }


# ---------------------------------------------------------------------------
# Scoring: deterministic + LLM judge
# ---------------------------------------------------------------------------

def extract_numbers(text: str) -> list[float]:
    """Extract all numbers from text."""
    # Match numbers like 1234, 1,234, 1234.56, $1,234.56, -5
    matches = re.findall(r'[-]?\$?[\d,]+\.?\d*', text)
    results = []
    for m in matches:
        try:
            clean = m.replace("$", "").replace(",", "")
            results.append(float(clean))
        except ValueError:
            pass
    return results


def deterministic_score(check: dict, answer: str) -> dict | None:
    """Try to score deterministically. Returns result dict or None if inconclusive."""
    check_type = check["type"]

    if check_type in ("exact_number", "percentage"):
        numbers = extract_numbers(answer)
        if not numbers:
            return None  # Inconclusive

        expected = check["value"]
        tolerance = check.get("tolerance", max(abs(expected * 0.05), 1) if check_type == "exact_number" else 2)

        best = min(numbers, key=lambda n: abs(n - expected))
        if abs(best - expected) <= tolerance:
            return {"correct": True, "partial": False, "method": "deterministic", "explanation": f"Found {best}, expected {expected} (tol {tolerance})"}

        # Check magnitude trap (100x off = cents vs dollars)
        mag = check.get("magnitude_trap")
        if mag and any(abs(n - expected * mag) / max(abs(expected * mag), 1) < 0.1 for n in numbers):
            return {"correct": False, "partial": True, "method": "deterministic", "explanation": f"Found value ~{mag}x off — likely unit conversion error"}

        # Close but not within tolerance
        if abs(best - expected) / max(abs(expected), 1) < 0.20:
            return {"correct": False, "partial": True, "method": "deterministic", "explanation": f"Found {best}, expected {expected} — close but outside tolerance"}

        return {"correct": False, "partial": False, "method": "deterministic", "explanation": f"Best match {best}, expected {expected}"}

    elif check_type == "contains_all":
        values = check["values"]
        found = [v for v in values if v.lower() in answer.lower()]
        if len(found) == len(values):
            return {"correct": True, "partial": False, "method": "deterministic", "explanation": "All required items found"}
        if len(found) >= len(values) * 0.6:
            return {"correct": False, "partial": True, "method": "deterministic", "explanation": f"Found {len(found)}/{len(values)} items"}
        return None  # Inconclusive, fall to judge

    return None


JUDGE_SYSTEM = """You are a benchmark evaluation judge. Compare an agent's response against the ground truth answer.

Scoring rules:
- "correct": the agent's answer contains the right information. Minor rounding differences are OK (e.g. $22,498 vs $22,500). Formatting doesn't matter.
- "partial": the agent got the right approach but the final number/list is materially wrong (>10% off for numbers, missing key items for lists).
- Neither correct nor partial: the answer is wrong, missing, or the agent failed to answer.

For dollar amounts: order of magnitude MUST be correct. $22,500 vs $2,250,000 (100x off, e.g. cents vs dollars) is WRONG, not partial.

Respond with ONLY a JSON object:
{"correct": true/false, "partial": true/false, "explanation": "one sentence reason"}"""


def llm_judge_score(api_key: str, question: str, expected, answer: str, explanation: str, judge_model: str) -> dict:
    prompt = f"""Question asked: {question}

Ground truth answer: {json.dumps(expected)}
Context about what makes this question tricky: {explanation}

Agent's full response:
---
{answer}
---

Is the agent's answer correct?"""

    try:
        resp = call_openrouter(api_key, judge_model, JUDGE_SYSTEM, [], [{"role": "user", "content": prompt}])
        text = resp["content"][0]["text"].strip() if resp["content"] else ""
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        result = json.loads(text)
        result["method"] = "llm_judge"
        result["judge_tokens"] = resp["input_tokens"] + resp["output_tokens"]
        return result
    except Exception as e:
        return {"correct": False, "partial": False, "method": "llm_judge", "explanation": f"Judge error: {e}", "judge_tokens": 0}


def score_answer(api_key: str, question_data: dict, answer: str, judge_model: str) -> dict:
    """Score an answer using LLM judge."""
    return llm_judge_score(
        api_key, question_data["question"], question_data["expected_answer"],
        answer, question_data.get("explanation", ""), judge_model,
    )


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score confidence interval for a proportion."""
    if trials == 0:
        return (0.0, 0.0)
    p = successes / trials
    denom = 1 + z**2 / trials
    center = (p + z**2 / (2 * trials)) / denom
    spread = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[dict], models_used: list[str], verticals_used: list[str], runs: int) -> str:
    lines = []
    lines.append("# Dinobase Benchmark Results")
    lines.append(f"\nRun: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Models: {', '.join(models_used)}")
    lines.append(f"Verticals: {', '.join(verticals_used)}")
    lines.append(f"Runs per question: {runs}")
    total_cost = sum(r.get("cost_usd", 0) for r in results)
    lines.append(f"Total cost: ${total_cost:.2f}")
    lines.append("")

    # Summary by model + approach
    lines.append("## Summary")
    lines.append("")
    lines.append("| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |")
    lines.append("|-------|----------|----------|--------|----------------|--------------|-------------|")

    for model in models_used:
        for approach in ["dinobase", "raw_mcp"]:
            ar = [r for r in results if r.get("model") == model and r["approach"] == approach]
            if not ar:
                continue
            correct = sum(1 for r in ar if r.get("judgment", {}).get("correct"))
            total = len(ar)
            tokens = sum(r["total_tokens"] for r in ar)
            cost = sum(r.get("cost_usd", 0) for r in ar)
            latency = sum(r["latency_ms"] for r in ar) / total if total else 0
            ci_lo, ci_hi = wilson_ci(correct, total)
            tpc = tokens // max(correct, 1)
            cpc = cost / max(correct, 1)
            label = "SQL" if approach == "dinobase" else "MCP"
            model_short = MODELS.get(model, ModelConfig(model, model)).display_name
            lines.append(f"| {model_short} | {label} | {correct}/{total} ({correct/total*100:.0f}%) | [{ci_lo:.0%}-{ci_hi:.0%}] | {tpc:,} | ${cpc:.3f} | {latency/1000:.1f}s |")

    # By vertical
    lines.append("")
    lines.append("## By Vertical")
    lines.append("")
    for v in verticals_used:
        lines.append(f"### {v.title()}")
        lines.append("")
        lines.append("| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |")
        lines.append("|-------|----------|-------------|---------------|-------------------|--------|")
        for model in models_used:
            for approach in ["dinobase", "raw_mcp"]:
                tier_stats = []
                for tier in [1, 2, 3]:
                    tar = [r for r in results if r.get("model") == model and r["approach"] == approach and r["tier"] == tier and r.get("vertical") == v]
                    if tar:
                        c = sum(1 for r in tar if r.get("judgment", {}).get("correct"))
                        tier_stats.append(f"{c}/{len(tar)}")
                    else:
                        tier_stats.append("—")
                ar = [r for r in results if r.get("model") == model and r["approach"] == approach and r.get("vertical") == v]
                tokens = sum(r["total_tokens"] for r in ar) if ar else 0
                if any(s != "—" for s in tier_stats):
                    label = "SQL" if approach == "dinobase" else "MCP"
                    model_short = MODELS.get(model, ModelConfig(model, model)).display_name
                    lines.append(f"| {model_short} | {label} | {tier_stats[0]} | {tier_stats[1]} | {tier_stats[2]} | {tokens:,} |")
        lines.append("")

    # Semantic traps
    trap_results = [r for r in results if r.get("semantic_trap")]
    if trap_results:
        lines.append("## Semantic Trap Analysis")
        lines.append("")
        lines.append("| Trap | Question | Model | Approach | Result |")
        lines.append("|------|----------|-------|----------|--------|")
        for r in trap_results:
            status = "PASS" if r.get("judgment", {}).get("correct") else "FAIL"
            model_short = MODELS.get(r.get("model", ""), ModelConfig("", "?")).display_name
            label = "SQL" if r["approach"] == "dinobase" else "MCP"
            lines.append(f"| {r['semantic_trap']} | {r['question'][:40]} | {model_short} | {label} | {status} |")
        lines.append("")

    return "\n".join(lines)


def results_to_csv(results: list[dict]) -> str:
    """Convert results to CSV format."""
    headers = ["question_id", "vertical", "tier", "model", "approach", "run", "correct", "partial",
               "tokens_input", "tokens_output", "tokens_total", "cost_usd", "latency_ms",
               "tool_calls", "scoring_method", "semantic_trap", "answer_excerpt"]
    rows = [",".join(headers)]
    for r in results:
        j = r.get("judgment", {})
        row = [
            r.get("question_id", ""), r.get("vertical", ""), str(r.get("tier", "")),
            r.get("model", ""), r.get("approach", ""), str(r.get("run", 0)),
            str(j.get("correct", False)), str(j.get("partial", False)),
            str(r.get("total_input_tokens", 0)), str(r.get("total_output_tokens", 0)),
            str(r.get("total_tokens", 0)), f"{r.get('cost_usd', 0):.4f}",
            str(r.get("latency_ms", 0)), str(r.get("tool_calls", 0)),
            j.get("method", "") or "", r.get("semantic_trap", "") or "",
            f'"{r.get("answer", "")[:100].replace(chr(34), chr(39))}"',
        ]
        rows.append(",".join(row))
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run Dinobase benchmark")
    parser.add_argument("--models", type=str, default="claude-sonnet-4.6", help="Comma-separated model keys or 'all'")
    parser.add_argument("--vertical", type=str, default="revops", help="Vertical name or 'all'")
    parser.add_argument("--approach", choices=["dinobase", "raw_mcp"], help="Run only one approach")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], help="Run only one tier")
    parser.add_argument("--question", type=str, help="Run only one question by ID")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help=f"Runs per question (default {DEFAULT_RUNS})")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help=f"Max spend in USD (default ${DEFAULT_BUDGET})")
    parser.add_argument("--judge-model", type=str, default=DEFAULT_JUDGE, help="Judge model ID")
    parser.add_argument("--dry-run", action="store_true", help="Show plan and cost estimate")
    parser.add_argument("--resume", action="store_true", help="Resume from last progress file")
    parser.add_argument("--output", type=str, help="Output file for results JSON")
    args = parser.parse_args()

    # Resolve models
    if args.models == "all":
        model_keys = list(MODELS.keys())
    else:
        model_keys = [m.strip() for m in args.models.split(",")]
        for k in model_keys:
            if k not in MODELS:
                print(f"Unknown model: {k}. Available: {', '.join(MODELS.keys())}")
                sys.exit(1)

    # Resolve verticals
    if args.vertical == "all":
        verticals = list(VERTICAL_SCHEMAS.keys())
    else:
        verticals = [v.strip() for v in args.vertical.split(",")]

    approaches = [args.approach] if args.approach else ["dinobase", "raw_mcp"]

    # Load questions
    with open(QUESTIONS_FILE) as f:
        data = json.load(f)

    all_questions = []
    for v in verticals:
        vdata = data.get("verticals", {}).get(v, {})
        for q in vdata.get("questions", []):
            q["_vertical"] = v
            if args.tier and q["tier"] != args.tier:
                continue
            if args.question and q["id"] != args.question:
                continue
            all_questions.append(q)

    # Check API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        sys.exit(1)

    total_runs = len(all_questions) * len(approaches) * len(model_keys) * args.runs
    print(f"\nBenchmark: {len(all_questions)} questions x {len(approaches)} approaches x {len(model_keys)} models x {args.runs} runs = {total_runs} API calls")

    # Estimate cost
    est_tokens_dinobase = 8000  # avg per question
    est_tokens_mcp = 40000  # avg per question
    est_total_cost = 0
    for mk in model_keys:
        mc = MODELS[mk]
        for approach in approaches:
            tokens = est_tokens_dinobase if approach == "dinobase" else est_tokens_mcp
            per_q = compute_cost(int(tokens * 0.8), int(tokens * 0.2), mc)
            est_total_cost += per_q * len(all_questions) * args.runs
    print(f"Estimated cost: ${est_total_cost:.2f} (budget: ${args.budget})")

    if args.dry_run:
        print(f"\n=== DRY RUN ===\n")
        print(f"Models: {', '.join(MODELS[k].display_name for k in model_keys)}")
        print(f"Verticals: {', '.join(verticals)}")
        print(f"Questions per vertical:")
        for v in verticals:
            vqs = [q for q in all_questions if q["_vertical"] == v]
            print(f"  {v}: {len(vqs)} ({sum(1 for q in vqs if q['tier']==1)} T1, {sum(1 for q in vqs if q['tier']==2)} T2, {sum(1 for q in vqs if q['tier']==3)} T3)")
        print(f"\nCost estimate by model:")
        for mk in model_keys:
            mc = MODELS[mk]
            model_cost = 0
            for approach in approaches:
                tokens = est_tokens_dinobase if approach == "dinobase" else est_tokens_mcp
                per_q = compute_cost(int(tokens * 0.8), int(tokens * 0.2), mc)
                model_cost += per_q * len(all_questions) * args.runs
            print(f"  {mc.display_name}: ~${model_cost:.2f}")
        print(f"\nTotal estimated: ${est_total_cost:.2f}")
        return

    # Generate test data if missing
    parquet_count = len(list(SAMPLE_DATA_DIR.glob("*.parquet")))
    if parquet_count == 0:
        print("No sample data found. Generating...")
        import subprocess
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "generate_sample_data.py")], check=True)

    # Set up real Dinobase instance (actual product, not a mock)
    print("\nSetting up Dinobase (real product)...")
    engine = setup_dinobase(verticals)
    print("  QueryEngine ready with real metadata and annotations")

    # Load raw API data for the MCP approach (in-memory, no database)
    print("Loading raw API data for MCP approach...")
    api_data = load_raw_api_data(verticals)
    total_api_records = sum(len(rows) for schema in api_data.values() for rows in schema.values())
    print(f"  {total_api_records} records loaded in memory")

    # Verify ground truth (separate plain DuckDB, not used during benchmark)
    print("\nVerifying ground truth SQL...")
    gt_conn = setup_ground_truth_db(verticals)
    gt_errors = 0
    for q in all_questions:
        try:
            result = gt_conn.execute(q["ground_truth_sql"]).fetchone()
        except Exception as e:
            print(f"  ERROR [{q['id']}]: {e}")
            print(f"    SQL: {q['ground_truth_sql']}")
            gt_errors += 1
    gt_conn.close()
    if gt_errors:
        print(f"\n{gt_errors} ground truth errors. Fix questions.json before running.")
        sys.exit(1)
    print(f"  All {len(all_questions)} ground truth queries OK")

    # Load previous results if resuming
    RESULTS_DIR.mkdir(exist_ok=True)
    all_results = []
    completed_keys = set()

    # Resume: load results from per-model JSON files
    if args.resume:
        for mf in RESULTS_DIR.glob("*.json"):
            try:
                with open(mf) as f:
                    model_results = json.load(f)
                all_results.extend(model_results)
            except (json.JSONDecodeError, Exception):
                pass
        completed_keys = {(r["question_id"], r["approach"], r.get("model", ""), r["run"]) for r in all_results}
        if all_results:
            models_loaded = set(r.get("model", "") for r in all_results)
            print(f"Resuming: {len(all_results)} results from {len(models_loaded)} models")

    # Run benchmark
    current = 0
    cumulative_cost = sum(r.get("cost_usd", 0) for r in all_results)
    budget_exceeded = False
    print()

    skip_models = set()  # models that fail repeatedly get skipped

    for run_idx in range(args.runs):
        if budget_exceeded:
            break
        for mk in model_keys:
            if budget_exceeded:
                break
            if mk in skip_models:
                continue
            mc = MODELS[mk]
            consecutive_errors = 0
            for q in all_questions:
                if budget_exceeded:
                    break
                for approach in approaches:
                    current += 1
                    key = (q["id"], approach, mk, run_idx)

                    if key in completed_keys:
                        continue

                    # Budget check
                    if cumulative_cost >= args.budget:
                        print(f"\nBudget limit reached (${cumulative_cost:.2f} / ${args.budget}). Stopping.")
                        budget_exceeded = True
                        break

                    run_label = f" run {run_idx+1}" if args.runs > 1 else ""
                    print(f"[{current}/{total_runs}] {q['id']} | {mc.display_name} | {approach}{run_label}: {q['question'][:55]}...")

                    result = run_question(api_key, engine, api_data, q["question"], approach, q["_vertical"], mc)

                    # Score
                    judgment = score_answer(api_key, q, result["answer"], args.judge_model)
                    cost = compute_cost(result["total_input_tokens"], result["total_output_tokens"], mc)
                    cumulative_cost += cost

                    # Save conversation trace to separate file for inspection
                    trace = result.pop("trace", [])
                    trace_dir = RESULTS_DIR / "traces" / mk
                    trace_dir.mkdir(parents=True, exist_ok=True)
                    trace_file = trace_dir / f"{q['id']}_{approach}.json"
                    with open(trace_file, "w") as f:
                        json.dump({
                            "question_id": q["id"], "question": q["question"],
                            "model": mk, "approach": approach,
                            "expected_answer": q["expected_answer"],
                            "judgment": judgment,
                            "trace": trace,
                        }, f, indent=2, default=str)

                    record = {
                        "question_id": q["id"], "question": q["question"],
                        "vertical": q["_vertical"], "tier": q["tier"],
                        "approach": approach, "model": mk, "run": run_idx,
                        "answer": result["answer"],
                        "expected_answer": q["expected_answer"],
                        "semantic_trap": q.get("semantic_trap"),
                        "judgment": judgment, "cost_usd": cost,
                        **{k: v for k, v in result.items() if k != "answer"},
                    }
                    all_results.append(record)

                    # Save incrementally — per-model file
                    model_results = [r for r in all_results if r.get("model") == mk]
                    with open(RESULTS_DIR / f"{mk}.json", "w") as f:
                        json.dump(model_results, f, indent=2, default=str)

                    status = "PASS" if judgment.get("correct") else ("partial" if judgment.get("partial") else "FAIL")
                    print(f"         {status} | {result['total_tokens']:,} tok | ${cost:.3f} | {result['tool_calls']} calls | {result['latency_ms']}ms")
                    if not judgment.get("correct"):
                        print(f"         {judgment.get('explanation', '')[:100]}")
                    print()

                    # Stop if a model keeps erroring — fix the issue and --resume
                    if result.get("error"):
                        consecutive_errors += 1
                        if consecutive_errors >= 3:
                            print(f"\n  STOPPING: {mc.display_name} failed {consecutive_errors} times in a row.")
                            print(f"  Error: {result['error'][:200]}")
                            print(f"  Fix the issue, then re-run with --resume to continue.\n")
                            budget_exceeded = True  # reuse flag to break all loops
                            break
                    else:
                        consecutive_errors = 0

    # Save per-model reports
    for mk in model_keys:
        model_results = [r for r in all_results if r.get("model") == mk]
        if not model_results:
            continue
        # JSON (already saved incrementally, but write final version)
        with open(RESULTS_DIR / f"{mk}.json", "w") as f:
            json.dump(model_results, f, indent=2, default=str)
        # Per-model report
        model_report = generate_report(model_results, [mk], verticals, args.runs)
        with open(RESULTS_DIR / f"{mk}.md", "w") as f:
            f.write(model_report)

    # Combined summary report
    report = generate_report(all_results, model_keys, verticals, args.runs)
    with open(RESULTS_DIR / "REPORT.md", "w") as f:
        f.write(report)

    print(f"\nResults saved to benchmarks/results/:")
    print(f"  REPORT.md          — combined summary across all models")
    for mk in model_keys:
        if any(r.get("model") == mk for r in all_results):
            print(f"  {mk}.md        — {MODELS[mk].display_name} details")
            print(f"  {mk}.json      — raw data")

    # Print summary
    print(f"\nTotal cost: ${cumulative_cost:.2f}")
    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
