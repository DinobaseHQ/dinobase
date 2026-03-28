# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: deepseek-v3.2
Verticals: revops
Runs per question: 1
Total cost: $0.59

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| DeepSeek V3.2 | SQL | 12/15 (80%) | [55%-93%] | 51,312 | $0.014 | 134.6s |
| DeepSeek V3.2 | MCP | 3/15 (20%) | [7%-45%] | 538,735 | $0.141 | 256.3s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| DeepSeek V3.2 | SQL | 4/5 | 5/5 | 3/5 | 615,755 |
| DeepSeek V3.2 | MCP | 2/5 | 0/5 | 1/5 | 1,616,207 |

## Semantic Trap Analysis

| Trap | Question | Model | Approach | Result |
|------|----------|-------|----------|--------|
| amounts_in_cents | I need our MRR number for the investor u | DeepSeek V3.2 | SQL | PASS |
| amounts_in_cents | I need our MRR number for the investor u | DeepSeek V3.2 | MCP | FAIL |
| win_rate_formula | The CEO is asking about our win rate — w | DeepSeek V3.2 | SQL | PASS |
| win_rate_formula | The CEO is asking about our win rate — w | DeepSeek V3.2 | MCP | FAIL |
| amounts_in_cents | Finance needs to know how much revenue w | DeepSeek V3.2 | SQL | PASS |
| amounts_in_cents | Finance needs to know how much revenue w | DeepSeek V3.2 | MCP | FAIL |
| amounts_in_cents | How much MRR are we getting from contact | DeepSeek V3.2 | SQL | PASS |
| amounts_in_cents | How much MRR are we getting from contact | DeepSeek V3.2 | MCP | FAIL |
| amounts_in_cents | I am prepping for the QBR — can you show | DeepSeek V3.2 | SQL | PASS |
| amounts_in_cents | I am prepping for the QBR — can you show | DeepSeek V3.2 | MCP | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | DeepSeek V3.2 | SQL | FAIL |
| amounts_in_cents | Which industry vertical is bringing in t | DeepSeek V3.2 | MCP | FAIL |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | DeepSeek V3.2 | SQL | PASS |
| amounts_in_cents | Pull me a report of our top 5 highest-sp | DeepSeek V3.2 | MCP | PASS |
