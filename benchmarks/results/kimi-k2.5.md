# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: kimi-k2.5
Verticals: revops
Runs per question: 1
Total cost: $0.75

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Kimi K2.5 | SQL | 11/15 (73%) | [48%-89%] | 24,713 | $0.015 | 71.2s |
| Kimi K2.5 | MCP | 7/15 (47%) | [25%-70%] | 161,648 | $0.084 | 174.8s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Kimi K2.5 | SQL | 2/5 | 5/5 | 4/5 | 271,846 |
| Kimi K2.5 | MCP | 3/5 | 2/5 | 2/5 | 1,131,538 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | Kimi K2.5 | SQL | PASS |
| amounts_in_cents | I need our MRR number for the investor u | Kimi K2.5 | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | Kimi K2.5 | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | Kimi K2.5 | MCP | FAIL |
| amounts_in_cents | Finance needs to know how much revenue w | Kimi K2.5 | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Kimi K2.5 | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | Kimi K2.5 | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | Kimi K2.5 | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | Kimi K2.5 | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | Kimi K2.5 | MCP | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Kimi K2.5 | SQL | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Kimi K2.5 | MCP | FAIL |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Kimi K2.5 | SQL | FAIL |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Kimi K2.5 | MCP | PASS |
