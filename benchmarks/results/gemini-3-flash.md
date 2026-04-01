# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: gemini-3-flash
Verticals: revops
Runs per question: 1
Total cost: $0.26

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Gemini 3 Flash | SQL | 12/15 (80%) | [55%-93%] | 8,167 | $0.005 | 7.8s |
| Gemini 3 Flash | MCP | 5/15 (33%) | [15%-58%] | 72,528 | $0.039 | 8.7s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Gemini 3 Flash | SQL | 4/5 | 4/5 | 4/5 | 98,007 |
| Gemini 3 Flash | MCP | 1/5 | 2/5 | 2/5 | 362,640 |

