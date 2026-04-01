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

