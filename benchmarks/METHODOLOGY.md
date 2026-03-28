# Benchmark Methodology

## What we measure

Whether an AI agent answers business questions more accurately and cheaply when it queries a unified SQL database (Dinobase) versus calling per-source MCP tools. Both approaches use the same data, same LLM, same questions. The only variable is how the agent accesses data.

## Dataset

5 verticals, each simulating a real business scenario with 2-3 separate SaaS tools that share customers:

| Vertical | Sources | Tables | Rows | Join Key |
|----------|---------|--------|------|----------|
| **RevOps** | HubSpot CRM + Stripe billing | 7 | ~1,400 | email |
| **E-commerce** | Shopify + Stripe payments | 5 | ~1,500 | email |
| **Knowledge Base** | Notion + GitHub + Slack | 6 | ~1,400 | username |
| **DevOps** | GitHub PRs + PagerDuty + Datadog | 5 | ~600 | service name |
| **Customer Support** | Zendesk + Stripe + Analytics | 5 | ~1,800 | email |

Total: ~6,300 rows across 28 tables. Cross-source overlap is ~75-85% (realistic).

All Stripe monetary fields are in cents. Shopify/HubSpot amounts are in dollars. This mismatch is a key semantic trap.

Data is deterministically generated with `faker` (seed=42) and stored as Parquet. Regenerate with:
```bash
python scripts/generate_sample_data.py
```

## Questions

75 questions across 3 tiers of difficulty, 15 per vertical (5 per tier):

### Tier 1: Simple (25 questions)
Single-source queries: counts, filters, aggregations. Every approach should get these right, but MCP uses far more tokens due to pagination (max 100 results per page).

### Tier 2: Semantic (25 questions)
Require domain knowledge: MRR calculation (cents to dollars + annualize), win rate formula, CSAT calculation, MTTR definition, etc. Each has a documented "semantic trap."

| Trap | What goes wrong | Error magnitude |
|------|----------------|-----------------|
| `amounts_in_cents` | Agent treats cents as dollars | 100x |
| `win_rate_formula` | Divides by total deals, not closed | ~2x |
| `csat_formula` | Counts offered/unoffered in denominator | ~1.5x |
| `mttr_only_resolved` | Includes unresolved incidents | Wrong |
| `pipeline_definition` | Includes closed deals | ~2x |
| `open_issues_stale` | Uses cached count instead of actual | Wrong |
| `thread_ts_semantics` | Counts thread replies as top-level | Wrong |

### Tier 3: Cross-source (25 questions)
Require joining data across 2+ sources. Impossible without SQL or manual in-context correlation of full JSON dumps.

All questions have ground truth SQL verified against the dataset. Published in `benchmarks/questions.json`.

## Approaches

### Dinobase (SQL)
3 tools: `list_sources`, `describe`, `query`. System prompt includes source metadata, column annotations ("amounts in cents"), and join key hints. Agent writes SQL against DuckDB.

### Per-Source MCP Tools
Dynamic per-vertical tool set (one `list_*` tool per table). Returns raw JSON, max 100 per page, with pagination. No semantic annotations, no cross-source joins, no aggregations.

### What's the same
- Same LLM (configurable, same model for both approaches)
- Same underlying data
- Same questions
- Same evaluation
- Same max turns (15), temperature (0)

### What's different

| | Dinobase | Per-Source MCP |
|--|----------|---------------|
| Data access | SQL queries | Paginated JSON |
| Aggregation | Database engine | Agent computes in-context |
| Cross-source joins | SQL JOIN | Agent correlates manually |
| Semantic metadata | Column annotations | None |
| Typical response | 100-500 chars | 5,000-60,000 chars |

## Models

10 models tested via OpenRouter (single API backend):

| Model | Provider | Tool-use |
|-------|----------|----------|
| Claude Sonnet 4.6 | Anthropic | Yes |
| Claude Opus 4.6 | Anthropic | Yes |
| GPT-5.4 | OpenAI | Yes |
| o4-mini | OpenAI | Yes |
| Gemini 3.1 Pro | Google | Yes |
| Grok 4.1 Fast | xAI | Yes |
| DeepSeek V3.2 | DeepSeek | Yes |
| Qwen 3.5 | Alibaba | Yes |
| Llama 4 Maverick | Meta | Yes |
| Mistral Large 3 | Mistral | Yes |

Pricing fetched live from OpenRouter API at startup. Models with weak tool-use gracefully degrade (3 consecutive failures = skip, reported as `tool_use_error_rate`).

## Scoring

### Deterministic (no API call, ~60% of questions)
- `exact_number`: Extract numbers via regex, compare within tolerance
- `percentage`: Compare within 2 percentage points
- `contains_all`: Case-insensitive substring check
- `magnitude_trap`: Detect 100x errors (cents vs dollars) → partial credit

### LLM Judge (remaining ~40%)
- Always a different model than the agent (avoids same-model bias)
- `temperature=0` for consistency

## Statistical rigor

- **N=3 runs** per question (configurable). LLMs are non-deterministic even at temperature=0.
- **Wilson score 95% confidence intervals** for accuracy (better than normal approximation for small N).
- **Token counts from API** — `response.usage.prompt_tokens` and `completion_tokens`, not estimated.
- **Real cost** from OpenRouter pricing, not approximated.

Key metrics:
- `accuracy`: correct_count / total
- `cost_per_correct_answer`: total_cost / correct_count
- `tokens_per_correct_answer`: total_tokens / correct_count

## Reproducibility

- `temperature=0`, `seed=42` on all API calls
- Deterministic dataset (fixed faker seed)
- Published questions, SQL, and scoring in `benchmarks/questions.json`
- Incremental saves to `_progress.json` (survives crashes and budget limits)

## Budget management

`--budget` flag stops gracefully when cumulative API cost exceeds the limit. Default: $25.

Estimated costs:
- Single model, 1 vertical, 3 runs: ~$1-5
- 3 models, all verticals, 3 runs: ~$15-20
- All 10 models, all verticals, 3 runs: ~$300

## How to run

```bash
# Validate infrastructure (no API key needed)
python benchmarks/validate.py

# Generate/regenerate test data
python scripts/generate_sample_data.py

# Quick test (one cheap model, one vertical)
export OPENROUTER_API_KEY=sk-or-...
python benchmarks/run_benchmark.py --models deepseek-v3.2 --vertical revops --runs 1

# Recommended run (3 models, all verticals)
python benchmarks/run_benchmark.py --models claude-sonnet-4.6,o4-mini,deepseek-v3.2 --vertical all --runs 3 --budget 20

# Full benchmark (all 10 models)
python benchmarks/run_benchmark.py --models all --vertical all --runs 3 --budget 300

# Cost estimate without running
python benchmarks/run_benchmark.py --dry-run --models all --vertical all

# Resume after crash/budget limit
python benchmarks/run_benchmark.py --resume
```

## File reference

```
scripts/
  generate_sample_data.py        # Data generator (faker + pyarrow, seed=42)

sample_data/
  *.parquet                      # 28 parquet files across 5 verticals

benchmarks/
  questions.json                 # 75 questions with ground truth SQL
  run_benchmark.py               # Multi-model runner, scoring, reporting
  validate.py                    # Infrastructure validation
  METHODOLOGY.md                 # This file
  results/
    benchmark_*_progress.json    # Incremental results
    benchmark_*_report.md        # Markdown reports
    benchmark_*.csv              # CSV for analysis
```
