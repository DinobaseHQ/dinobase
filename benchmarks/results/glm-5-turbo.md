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

