# Dinobase Benchmark Results

Run: 2026-03-26 05:48 UTC
Models: claude-opus-4.6
Verticals: revops
Runs per question: 1
Total cost: $9.44

## Summary

| Model | Approach | Accuracy | 95% CI | Tokens/Correct | Cost/Correct | Avg Latency |
|-------|----------|----------|--------|----------------|--------------|-------------|
| Claude Opus 4.6 | SQL | 14/15 (93%) | [70%-99%] | 12,952 | $0.087 | 23.7s |
| Claude Opus 4.6 | MCP | 5/15 (33%) | [15%-58%] | 312,314 | $1.646 | 234.7s |

## By Vertical

### Revops

| Model | Approach | T1 (Simple) | T2 (Semantic) | T3 (Cross-Source) | Tokens |
|-------|----------|-------------|---------------|-------------------|--------|
| Claude Opus 4.6 | SQL | 5/5 | 5/5 | 4/5 | 181,329 |
| Claude Opus 4.6 | MCP | 2/5 | 1/5 | 2/5 | 1,561,571 |

