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

