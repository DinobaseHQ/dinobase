# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: glm-5-turbo
Verticals: revops
Runs per question: 1
Total cost: $2.64

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| GLM-5 Turbo | SQL | 13/15 (87%) | [62%-96%] | 8,917 | $0.013 | 12.4s |
| GLM-5 Turbo | MCP | 3/15 (20%) | [7%-45%] | 577,379 | $0.824 | 55.8s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| GLM-5 Turbo | SQL | 4/5 | 5/5 | 4/5 | 115,923 |
| GLM-5 Turbo | MCP | 2/5 | 0/5 | 1/5 | 1,732,138 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | GLM-5 Turbo | SQL | PASS |
| amounts_in_cents | I need our MRR number for the investor u | GLM-5 Turbo | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | GLM-5 Turbo | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | GLM-5 Turbo | MCP | FAIL |
| amounts_in_cents | Finance needs to know how much revenue w | GLM-5 Turbo | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | GLM-5 Turbo | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | GLM-5 Turbo | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | GLM-5 Turbo | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | GLM-5 Turbo | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | GLM-5 Turbo | MCP | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | GLM-5 Turbo | SQL | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | GLM-5 Turbo | MCP | FAIL |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | GLM-5 Turbo | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | GLM-5 Turbo | MCP | PASS |
