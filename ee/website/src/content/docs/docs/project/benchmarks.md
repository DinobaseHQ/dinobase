---
title: Benchmark
description: How Dinobase SQL compares to per-source MCP tools across 11 LLMs on accuracy, cost, and speed.
---

We benchmarked Dinobase SQL against per-source MCP tools across 11 LLMs and 15 RevOps business questions. Same models, same data, same questions — only the data access method differs.

## Results

| Metric | Dinobase (SQL) | Per-Source MCP |
|--------|---------------|---------------|
| **Accuracy** | **91%** | 35% |
| **Avg latency** | **34s** | 106s |
| **Cost per correct answer** | **$0.027** | $0.445 |

56 percentage points more accurate, 3x faster, 16x cheaper per correct answer — consistent across all 11 models tested.

## Why the gap

**No cross-source joins.** Per-source MCP tools expose one tool per table. Questions that span two SaaS tools — "which customers have open HubSpot deals and failed Stripe charges?" — require an agent to manually correlate two JSON responses. This is error-prone and frequently exceeds context limits. With Dinobase, the agent writes one SQL `JOIN`.

**No semantic metadata.** MCP tools return raw data with no column descriptions. Without knowing what fields mean, agents misinterpret units, formulas, and aggregations — producing systematically wrong answers. Dinobase attaches column descriptions extracted from source API schemas.

**Pagination overhead.** Counting 1,000 records over MCP requires 10 round trips. SQL returns a single aggregate. The latency difference is primarily from models that make many MCP calls before running out of turns or context.

## Per-model breakdown

| Model | SQL Accuracy | MCP Accuracy | Gap | SQL $/Correct | MCP $/Correct |
|-------|-------------|-------------|-----|--------------|--------------|
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

- **15 questions** across 3 tiers: simple (single-source counts/filters), semantic (MRR, win rate, CSAT — requires domain knowledge), and cross-source (require joining HubSpot and Stripe data)
- **Scoring**: deterministic for ~60% of questions (regex number extraction with tolerance), LLM-as-judge (Claude Haiku 4.5) for the rest
- **Cost per correct answer**: total API cost divided by number of correct answers — this penalizes approaches that spend tokens on wrong answers
- **Total benchmark cost**: $29.44 across all 11 models via OpenRouter

Full dataset, questions, ground truth SQL, and scoring details: [benchmarks/README.md](https://github.com/DinobaseHQ/dinobase/blob/main/benchmarks/README.md).
