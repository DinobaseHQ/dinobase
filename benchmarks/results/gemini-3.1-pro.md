# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: gemini-3.1-pro
Verticals: revops
Runs per question: 1
Total cost: $5.69

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Gemini 3.1 Pro | SQL | 12/15 (80%) | [55%-93%] | 22,488 | $0.063 | 42.1s |
| Gemini 3.1 Pro | MCP | 6/15 (40%) | [20%-64%] | 343,260 | $0.822 | 86.2s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Gemini 3.1 Pro | SQL | 3/5 | 5/5 | 4/5 | 269,865 |
| Gemini 3.1 Pro | MCP | 2/5 | 4/5 | 0/5 | 2,059,564 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | Gemini 3.1 Pro | SQL | PASS |
| amounts_in_cents | I need our MRR number for the investor u | Gemini 3.1 Pro | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | Gemini 3.1 Pro | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | Gemini 3.1 Pro | MCP | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Gemini 3.1 Pro | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | Gemini 3.1 Pro | MCP | PASS |
| amounts_in_cents | How much MRR are we getting from contact | Gemini 3.1 Pro | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | Gemini 3.1 Pro | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | Gemini 3.1 Pro | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | Gemini 3.1 Pro | MCP | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | Gemini 3.1 Pro | SQL | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | Gemini 3.1 Pro | MCP | FAIL |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Gemini 3.1 Pro | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | Gemini 3.1 Pro | MCP | FAIL |
