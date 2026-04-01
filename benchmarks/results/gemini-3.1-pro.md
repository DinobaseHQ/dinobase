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

