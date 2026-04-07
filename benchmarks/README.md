# Dinobase Benchmark

11 LLMs, 75 questions, two approaches. Same models, same data — only data access differs.

## Results

| Metric | Dinobase (SQL) | Per-Source MCP |
|--------|---------------|---------------|
| **Accuracy** | **91%** | 35% |
| **Avg latency** | **34s** | 106s |
| **Cost per correct answer** | **$0.027** | $0.445 |

**56pp more accurate, 3x faster, 16x cheaper per correct answer — across every model tested.**

## Why the gap

**No cross-source joins.** Answering questions that span HubSpot + Stripe requires correlating two JSON responses manually. With Dinobase, one SQL `JOIN`.

**No semantic metadata.** No column descriptions means agents misinterpret field semantics — wrong units, wrong formulas, wrong aggregations. Dinobase attaches descriptions from source schemas.

**Pagination overhead.** 1,000 records over MCP = 10 round trips, ~60,000 tokens. SQL = one aggregate.

## Per-model results

| Model | SQL | MCP | Gap | SQL $/Correct | MCP $/Correct |
|-------|-----|-----|-----|--------------|--------------|
| Claude Opus 4.6 | **100%** | 33% | +67pp | $0.081 | $1.646 |
| Claude Sonnet 4.6 | **100%** | 53% | +47pp | $0.046 | $0.661 |
| Claude Haiku 4.5 | **93%** | 33% | +60pp | $0.020 | $0.149 |
| DeepSeek V3.2 | **93%** | 20% | +73pp | $0.012 | $0.141 |
| GLM-5 Turbo | **93%** | 20% | +73pp | $0.012 | $0.824 |
| MiniMax M2.7 | **93%** | 27% | +67pp | $0.005 | $0.131 |
| Gemini 3 Flash | **87%** | 33% | +53pp | $0.005 | $0.039 |
| Gemini 3.1 Pro | **87%** | 40% | +47pp | $0.059 | $0.822 |
| GPT 5.4 | **87%** | 40% | +47pp | $0.036 | $0.278 |
| Qwen 3.5 27B | **87%** | 33% | +53pp | $0.004 | $0.056 |
| Kimi K2.5 | **80%** | 47% | +33pp | $0.013 | $0.084 |

## Methodology

**Data**: HubSpot CRM + Stripe billing, ~1,400 rows, 7 tables, generated with `faker` (seed=42).

**Questions**: 15 across 3 tiers — simple (single-source counts/filters), semantic (MRR, win rate — require domain knowledge), cross-source (require joins). Ground truth SQL in [`questions.json`](questions.json).

**Scoring**: deterministic for ~60% (regex number extraction + tolerance), LLM-as-judge (Claude Haiku 4.5) for the rest. Cost per correct answer = total API cost / correct answers — penalizes spending tokens on wrong answers.

**Total cost**: $29.44 across all 11 models via OpenRouter.

## Reproduce

```bash
export OPENROUTER_API_KEY=sk-or-...
python benchmarks/run_benchmark.py --models deepseek-v3.2 --vertical revops --runs 1
python benchmarks/generate_report.py  # regenerate results/REPORT.md
```

Full results and failure analysis: [`results/REPORT.md`](results/REPORT.md).
