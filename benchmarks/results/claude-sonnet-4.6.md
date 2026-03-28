# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: claude-sonnet-4.6
Verticals: revops
Runs per question: 1
Total cost: $5.98

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Claude Sonnet 4.6 | SQL | 15/15 (100%) | [80%-100%] | 11,485 | $0.046 | 19.3s |
| Claude Sonnet 4.6 | MCP | 8/15 (53%) | [30%-75%] | 210,288 | $0.661 | 32.1s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Claude Sonnet 4.6 | SQL | 5/5 | 5/5 | 5/5 | 172,278 |
| Claude Sonnet 4.6 | MCP | 3/5 | 2/5 | 3/5 | 1,682,310 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | Claude Sonnet 4.6 | SQL | PASS |
| amounts_in_cents | I need our MRR number for the investor u | Claude Sonnet 4.6 | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | Claude Sonnet 4.6 | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | Claude Sonnet 4.6 | MCP | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Claude Sonnet 4.6 | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Claude Sonnet 4.6 | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | Claude Sonnet 4.6 | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | Claude Sonnet 4.6 | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | Claude Sonnet 4.6 | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | Claude Sonnet 4.6 | MCP | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Claude Sonnet 4.6 | SQL | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Claude Sonnet 4.6 | MCP | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Claude Sonnet 4.6 | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Claude Sonnet 4.6 | MCP | PASS |
