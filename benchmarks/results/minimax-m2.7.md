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

