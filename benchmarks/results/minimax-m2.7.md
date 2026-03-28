# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: minimax-m2.7
Verticals: revops
Runs per question: 1
Total cost: $0.59

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| MiniMax M2.7 | SQL | 12/15 (80%) | [55%-93%] | 15,910 | $0.006 | 23.6s |
| MiniMax M2.7 | MCP | 4/15 (27%) | [11%-52%] | 382,850 | $0.131 | 97.6s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| MiniMax M2.7 | SQL | 5/5 | 4/5 | 3/5 | 190,928 |
| MiniMax M2.7 | MCP | 1/5 | 1/5 | 2/5 | 1,531,401 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | MiniMax M2.7 | SQL | FAIL |
| amounts_in_cents | I need our MRR number for the investor u | MiniMax M2.7 | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | MiniMax M2.7 | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | MiniMax M2.7 | MCP | FAIL |
| amounts_in_cents | Finance needs to know how much revenue w | MiniMax M2.7 | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | MiniMax M2.7 | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | MiniMax M2.7 | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | MiniMax M2.7 | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | MiniMax M2.7 | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | MiniMax M2.7 | MCP | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | MiniMax M2.7 | SQL | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | MiniMax M2.7 | MCP | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | MiniMax M2.7 | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | MiniMax M2.7 | MCP | PASS |
