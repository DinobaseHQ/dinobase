# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: gemini-3-flash
Verticals: revops
Runs per question: 1
Total cost: $0.26

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Gemini 3 Flash | SQL | 12/15 (80%) | [55%-93%] | 8,167 | $0.005 | 7.8s |
| Gemini 3 Flash | MCP | 5/15 (33%) | [15%-58%] | 72,528 | $0.039 | 8.7s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Gemini 3 Flash | SQL | 4/5 | 4/5 | 4/5 | 98,007 |
| Gemini 3 Flash | MCP | 1/5 | 2/5 | 2/5 | 362,640 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | Gemini 3 Flash | SQL | FAIL |
| amounts_in_cents | I need our MRR number for the investor u | Gemini 3 Flash | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | Gemini 3 Flash | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | Gemini 3 Flash | MCP | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Gemini 3 Flash | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Gemini 3 Flash | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | Gemini 3 Flash | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | Gemini 3 Flash | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | Gemini 3 Flash | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | Gemini 3 Flash | MCP | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Gemini 3 Flash | SQL | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | Gemini 3 Flash | MCP | FAIL |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Gemini 3 Flash | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Gemini 3 Flash | MCP | PASS |
