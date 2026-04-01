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

