# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: claude-opus-4.6
Verticals: revops
Runs per question: 1
Total cost: $9.44

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Claude Opus 4.6 | SQL | 14/15 (93%) | [70%-99%] | 12,952 | $0.087 | 23.7s |
| Claude Opus 4.6 | MCP | 5/15 (33%) | [15%-58%] | 312,314 | $1.646 | 234.7s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Claude Opus 4.6 | SQL | 5/5 | 5/5 | 4/5 | 181,329 |
| Claude Opus 4.6 | MCP | 2/5 | 1/5 | 2/5 | 1,561,571 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | Claude Opus 4.6 | SQL | PASS |
| amounts_in_cents | I need our MRR number for the investor u | Claude Opus 4.6 | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | Claude Opus 4.6 | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | Claude Opus 4.6 | MCP | FAIL |
| amounts_in_cents | Finance needs to know how much revenue w | Claude Opus 4.6 | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Claude Opus 4.6 | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | Claude Opus 4.6 | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | Claude Opus 4.6 | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | Claude Opus 4.6 | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | Claude Opus 4.6 | MCP | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Claude Opus 4.6 | SQL | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Claude Opus 4.6 | MCP | FAIL |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Claude Opus 4.6 | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Claude Opus 4.6 | MCP | PASS |
