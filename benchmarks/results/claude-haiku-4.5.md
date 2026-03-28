# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: claude-haiku-4.5
Verticals: revops
Runs per question: 1
Total cost: $1.03

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Claude Haiku 4.5 | SQL | 12/15 (80%) | [55%-93%] | 20,106 | $0.024 | 10.5s |
| Claude Haiku 4.5 | MCP | 5/15 (33%) | [15%-58%] | 140,134 | $0.149 | 10.0s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Claude Haiku 4.5 | SQL | 4/5 | 4/5 | 4/5 | 241,282 |
| Claude Haiku 4.5 | MCP | 2/5 | 1/5 | 2/5 | 700,674 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | Claude Haiku 4.5 | SQL | PASS |
| amounts_in_cents | I need our MRR number for the investor u | Claude Haiku 4.5 | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | Claude Haiku 4.5 | SQL | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | Claude Haiku 4.5 | MCP | FAIL |
| amounts_in_cents | Finance needs to know how much revenue w | Claude Haiku 4.5 | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Claude Haiku 4.5 | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | Claude Haiku 4.5 | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | Claude Haiku 4.5 | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | Claude Haiku 4.5 | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | Claude Haiku 4.5 | MCP | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Claude Haiku 4.5 | SQL | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | Claude Haiku 4.5 | MCP | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Claude Haiku 4.5 | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Claude Haiku 4.5 | MCP | FAIL |
