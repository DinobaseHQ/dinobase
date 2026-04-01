# Dinobase Benchmark Results

Run: 2026-03-25 23:21 UTC
Models: qwen-3.5-27b
Verticals: revops
Runs per question: 1
Total cost: $0.33

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Qwen 3.5 27B | SQL | 12/15 (80%) | [55%-93%] | 15,716 | $0.004 | 15.3s |
| Qwen 3.5 27B | MCP | 5/15 (33%) | [15%-58%] | 182,104 | $0.056 | 198.2s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Qwen 3.5 27B | SQL | 4/5 | 4/5 | 4/5 | 188,601 |
| Qwen 3.5 27B | MCP | 1/5 | 2/5 | 2/5 | 910,520 |

