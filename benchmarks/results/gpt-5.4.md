# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: gpt-5.4
Verticals: revops
Runs per question: 1
Total cost: $2.14

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| GPT-5.4 | SQL | 13/15 (87%) | [62%-96%] | 10,560 | $0.036 | 10.7s |
| GPT-5.4 | MCP | 6/15 (40%) | [20%-64%] | 105,751 | $0.278 | 9.4s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| GPT-5.4 | SQL | 5/5 | 4/5 | 4/5 | 137,283 |
| GPT-5.4 | MCP | 2/5 | 1/5 | 3/5 | 634,511 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | GPT-5.4 | SQL | FAIL |
| amounts_in_cents | I need our MRR number for the investor u | GPT-5.4 | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | GPT-5.4 | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | GPT-5.4 | MCP | FAIL |
| amounts_in_cents | Finance needs to know how much revenue w | GPT-5.4 | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | GPT-5.4 | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | GPT-5.4 | SQL | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | GPT-5.4 | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | GPT-5.4 | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | GPT-5.4 | MCP | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | GPT-5.4 | SQL | PASS |
| amounts_in_cents | Which industry vertical is bringing in t | GPT-5.4 | MCP | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | GPT-5.4 | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | GPT-5.4 | MCP | PASS |
