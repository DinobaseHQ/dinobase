#!/usr/bin/env python3
"""
Generate the final benchmark report with charts and headline numbers.

Reads per-model JSON results from benchmarks/results/ and produces:
  - benchmarks/results/REPORT.md   (full markdown report with inline charts)
  - benchmarks/results/charts/     (PNG charts)

Usage:
    python benchmarks/generate_report.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
CHARTS_DIR = RESULTS_DIR / "charts"


def load_results() -> list[dict]:
    results = []
    for f in RESULTS_DIR.glob("*.json"):
        if "_old" in f.name:
            continue
        results.extend(json.load(open(f)))
    return results


def generate_charts(results: list[dict]):
    """Generate PNG charts using matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        print("  matplotlib not installed — skipping charts. pip install matplotlib")
        return False

    CHARTS_DIR.mkdir(exist_ok=True)

    # Prepare per-model stats
    models = sorted(set(r["model"] for r in results))
    model_labels = {
        "qwen-3.5-27b": "Qwen 3.5\n27B",
        "minimax-m2.7": "MiniMax\nM2.7",
        "gemini-3-flash": "Gemini 3\nFlash",
        "claude-haiku-4.5": "Claude\nHaiku 4.5",
        "glm-5-turbo": "GLM-5\nTurbo",
        "deepseek-v3.2": "DeepSeek\nV3.2",
        "kimi-k2.5": "Kimi\nK2.5",
        "gpt-5.4": "GPT\n5.4",
        "gemini-3.1-pro": "Gemini\n3.1 Pro",
        "claude-sonnet-4.6": "Claude\nSonnet 4.6",
        "claude-opus-4.6": "Claude\nOpus 4.6",
    }

    stats = {}
    for m in models:
        mr = [r for r in results if r["model"] == m]
        d = [r for r in mr if r["approach"] == "dinobase"]
        mcp = [r for r in mr if r["approach"] == "raw_mcp"]
        stats[m] = {
            "sql_acc": sum(1 for r in d if r.get("judgment", {}).get("correct")) / max(len(d), 1) * 100,
            "mcp_acc": sum(1 for r in mcp if r.get("judgment", {}).get("correct")) / max(len(mcp), 1) * 100,
            "sql_tokens": sum(r.get("total_tokens", 0) for r in d),
            "mcp_tokens": sum(r.get("total_tokens", 0) for r in mcp),
            "sql_cost": sum(r.get("cost_usd", 0) for r in d),
            "mcp_cost": sum(r.get("cost_usd", 0) for r in mcp),
            "sql_latency": sum(r.get("latency_ms", 0) for r in d) / max(len(d), 1) / 1000,
            "mcp_latency": sum(r.get("latency_ms", 0) for r in mcp) / max(len(mcp), 1) / 1000,
        }

    bar_width = 0.35
    colors = {"sql": "#2563eb", "mcp": "#dc2626"}

    def sorted_chart(sort_key, reverse=False):
        """Return models sorted by sort_key, with matching labels and x positions."""
        order = sorted(models, key=lambda m: stats[m][sort_key], reverse=reverse)
        lbls = [model_labels.get(m, m) for m in order]
        xpos = range(len(order))
        return order, lbls, xpos

    # --- Chart 1: Accuracy (sorted low to high by SQL accuracy) ---
    order, lbls, xpos = sorted_chart("sql_acc")
    fig, ax = plt.subplots(figsize=(14, 6))
    sql_acc = [stats[m]["sql_acc"] for m in order]
    mcp_acc = [stats[m]["mcp_acc"] for m in order]
    bars1 = ax.bar([i - bar_width/2 for i in xpos], sql_acc, bar_width, label="Dinobase (SQL)", color=colors["sql"])
    bars2 = ax.bar([i + bar_width/2 for i in xpos], mcp_acc, bar_width, label="Per-Source MCP", color=colors["mcp"])
    ax.set_ylabel("Accuracy (%)", fontsize=12)
    ax.set_title("Accuracy: Dinobase SQL vs Per-Source MCP Tools", fontsize=14, fontweight="bold")
    ax.set_xticks(list(xpos))
    ax.set_xticklabels(lbls, fontsize=9)
    ax.set_ylim(0, 110)
    ax.legend(fontsize=11)
    ax.bar_label(bars1, fmt="%.0f%%", fontsize=8, padding=2)
    ax.bar_label(bars2, fmt="%.0f%%", fontsize=8, padding=2)
    ax.axhline(y=sum(sql_acc)/len(sql_acc), color=colors["sql"], linestyle="--", alpha=0.4, linewidth=1)
    ax.axhline(y=sum(mcp_acc)/len(mcp_acc), color=colors["mcp"], linestyle="--", alpha=0.4, linewidth=1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "accuracy.png", dpi=150)
    plt.close()

    # --- Chart 2: Token usage (sorted low to high by SQL tokens) ---
    order, lbls, xpos = sorted_chart("sql_tokens")
    fig, ax = plt.subplots(figsize=(14, 6))
    sql_tok = [stats[m]["sql_tokens"] / 1000 for m in order]
    mcp_tok = [stats[m]["mcp_tokens"] / 1000 for m in order]
    bars1 = ax.bar([i - bar_width/2 for i in xpos], sql_tok, bar_width, label="Dinobase (SQL)", color=colors["sql"])
    bars2 = ax.bar([i + bar_width/2 for i in xpos], mcp_tok, bar_width, label="Per-Source MCP", color=colors["mcp"])
    ax.set_ylabel("Total Tokens (thousands)", fontsize=12)
    ax.set_title("Token Usage: Dinobase SQL vs Per-Source MCP Tools", fontsize=14, fontweight="bold")
    ax.set_xticks(list(xpos))
    ax.set_xticklabels(lbls, fontsize=9)
    ax.legend(fontsize=11)
    ax.bar_label(bars1, fmt="%.0fK", fontsize=7, padding=2)
    ax.bar_label(bars2, fmt="%.0fK", fontsize=7, padding=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "tokens.png", dpi=150)
    plt.close()

    # --- Chart 3: Cost per correct answer (sorted low to high by SQL cost/correct) ---
    cpc_stats = {}
    for m in models:
        d = [r for r in results if r["model"] == m and r["approach"] == "dinobase"]
        mcp = [r for r in results if r["model"] == m and r["approach"] == "raw_mcp"]
        dc = max(sum(1 for r in d if r.get("judgment", {}).get("correct")), 1)
        mc = max(sum(1 for r in mcp if r.get("judgment", {}).get("correct")), 1)
        cpc_stats[m] = {
            "sql_cpc": stats[m]["sql_cost"] / dc * 1000,
            "mcp_cpc": stats[m]["mcp_cost"] / mc * 1000,
        }

    order = sorted(models, key=lambda m: cpc_stats[m]["sql_cpc"])
    lbls = [model_labels.get(m, m) for m in order]
    xpos = range(len(order))
    fig, ax = plt.subplots(figsize=(14, 6))
    sql_cpc = [cpc_stats[m]["sql_cpc"] for m in order]
    mcp_cpc = [cpc_stats[m]["mcp_cpc"] for m in order]
    bars1 = ax.bar([i - bar_width/2 for i in xpos], sql_cpc, bar_width, label="Dinobase (SQL)", color=colors["sql"])
    bars2 = ax.bar([i + bar_width/2 for i in xpos], mcp_cpc, bar_width, label="Per-Source MCP", color=colors["mcp"])
    ax.set_ylabel("Cost per Correct Answer ($ × 10⁻³)", fontsize=12)
    ax.set_title("Cost Efficiency: Cost per Correct Answer", fontsize=14, fontweight="bold")
    ax.set_xticks(list(xpos))
    ax.set_xticklabels(lbls, fontsize=9)
    ax.legend(fontsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "cost_per_correct.png", dpi=150)
    plt.close()

    # --- Chart 4: Average latency per question (sorted low to high by SQL latency) ---
    order = sorted(models, key=lambda m: stats[m]["sql_latency"])
    lbls = [model_labels.get(m, m) for m in order]
    xpos = range(len(order))
    fig, ax = plt.subplots(figsize=(14, 6))
    sql_lat = [stats[m]["sql_latency"] for m in order]
    mcp_lat = [stats[m]["mcp_latency"] for m in order]
    bars1 = ax.bar([i - bar_width/2 for i in xpos], sql_lat, bar_width, label="Dinobase (SQL)", color=colors["sql"])
    bars2 = ax.bar([i + bar_width/2 for i in xpos], mcp_lat, bar_width, label="Per-Source MCP", color=colors["mcp"])
    ax.set_ylabel("Avg Latency per Question (seconds)", fontsize=12)
    ax.set_title("Latency: Dinobase SQL vs Per-Source MCP Tools", fontsize=14, fontweight="bold")
    ax.set_xticks(list(xpos))
    ax.set_xticklabels(lbls, fontsize=9)
    ax.legend(fontsize=11)
    ax.bar_label(bars1, fmt="%.0fs", fontsize=7, padding=2)
    ax.bar_label(bars2, fmt="%.0fs", fontsize=7, padding=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "latency.png", dpi=150)
    plt.close()

    print(f"  Charts saved to {CHARTS_DIR}/")
    return True


def generate_report(results: list[dict]) -> str:
    lines = []

    # Compute headline numbers
    all_sql = [r for r in results if r["approach"] == "dinobase"]
    all_mcp = [r for r in results if r["approach"] == "raw_mcp"]
    sql_correct = sum(1 for r in all_sql if r.get("judgment", {}).get("correct"))
    mcp_correct = sum(1 for r in all_mcp if r.get("judgment", {}).get("correct"))
    sql_acc = sql_correct / max(len(all_sql), 1) * 100
    mcp_acc = mcp_correct / max(len(all_mcp), 1) * 100
    sql_tokens = sum(r.get("total_tokens", 0) for r in all_sql)
    mcp_tokens = sum(r.get("total_tokens", 0) for r in all_mcp)
    sql_cost = sum(r.get("cost_usd", 0) for r in all_sql)
    mcp_cost = sum(r.get("cost_usd", 0) for r in all_mcp)
    sql_cost_per_correct = sql_cost / max(sql_correct, 1)
    mcp_cost_per_correct = mcp_cost / max(mcp_correct, 1)
    token_ratio = mcp_tokens / max(sql_tokens, 1)
    cost_ratio = mcp_cost_per_correct / max(sql_cost_per_correct, 0.0001)
    accuracy_gap = sql_acc - mcp_acc
    sql_avg_latency = sum(r.get("latency_ms", 0) for r in all_sql) / max(len(all_sql), 1) / 1000
    mcp_avg_latency = sum(r.get("latency_ms", 0) for r in all_mcp) / max(len(all_mcp), 1) / 1000
    latency_ratio = mcp_avg_latency / max(sql_avg_latency, 0.001)
    models = sorted(set(r["model"] for r in results))

    lines.append("# Dinobase Benchmark Results")
    lines.append("")
    lines.append(f"**{len(models)} models** tested on **15 RevOps questions** (HubSpot CRM + Stripe billing)")
    lines.append(f"comparing Dinobase SQL queries vs per-source MCP tools.")
    lines.append("")

    # Headline numbers
    lines.append("## Headline Numbers")
    lines.append("")
    lines.append(f"| Metric | Dinobase (SQL) | Per-Source MCP | Difference |")
    lines.append(f"|--------|---------------|---------------|------------|")
    lines.append(f"| **Accuracy** | **{sql_acc:.0f}%** ({sql_correct}/{len(all_sql)}) | {mcp_acc:.0f}% ({mcp_correct}/{len(all_mcp)}) | **+{accuracy_gap:.0f} percentage points** |")
    lines.append(f"| **Tokens per question** | {sql_tokens // len(all_sql):,} | {mcp_tokens // len(all_mcp):,} | **{token_ratio:.1f}x fewer** |")
    lines.append(f"| **Avg latency** | {sql_avg_latency:.1f}s | {mcp_avg_latency:.1f}s | **{latency_ratio:.1f}x faster** |")
    lines.append(f"| **Cost per correct answer** | ${sql_cost_per_correct:.4f} | ${mcp_cost_per_correct:.4f} | **{cost_ratio:.1f}x cheaper** |")
    lines.append("")
    lines.append(f"*Cost per correct answer = total API cost for an approach / number of questions it answered correctly.*")
    lines.append(f"*This penalizes approaches that spend tokens but get wrong answers — wasted compute.*")
    lines.append("")

    # The 4 numbers
    lines.append("### The numbers that matter")
    lines.append("")
    lines.append(f"1. **{accuracy_gap:.0f} percentage points more accurate** — Dinobase SQL gets {sql_acc:.0f}% right vs {mcp_acc:.0f}% for per-source MCP tools, across {len(models)} different LLMs")
    lines.append(f"2. **{token_ratio:.0f}x fewer tokens** — SQL queries return precise answers; MCP tools dump raw JSON that fills the context window")
    lines.append(f"3. **{latency_ratio:.1f}x faster** — {sql_avg_latency:.0f}s avg vs {mcp_avg_latency:.0f}s because SQL needs fewer round trips")
    lines.append(f"4. **{cost_ratio:.0f}x cheaper per correct answer** — fewer tokens + higher accuracy + less wasted compute")
    lines.append("")

    # Charts
    if (CHARTS_DIR / "accuracy.png").exists():
        lines.append("## Charts")
        lines.append("")
        lines.append("### Accuracy")
        lines.append("![Accuracy](charts/accuracy.png)")
        lines.append("")
        lines.append("### Token Usage")
        lines.append("![Tokens](charts/tokens.png)")
        lines.append("")
        lines.append("### Cost per Correct Answer")
        lines.append("![Cost](charts/cost_per_correct.png)")
        lines.append("")
        lines.append("### Latency")
        lines.append("![Latency](charts/latency.png)")
        lines.append("")

    # Per-model table
    lines.append("## Per-Model Results")
    lines.append("")
    lines.append("| Model | SQL Accuracy | MCP Accuracy | Gap | SQL Tokens | MCP Tokens | Token Ratio | SQL Cost | MCP Cost |")
    lines.append("|-------|-------------|-------------|-----|-----------|-----------|------------|---------|---------|")
    for m in models:
        d = [r for r in results if r["model"] == m and r["approach"] == "dinobase"]
        mcp = [r for r in results if r["model"] == m and r["approach"] == "raw_mcp"]
        dc = sum(1 for r in d if r.get("judgment", {}).get("correct"))
        mc = sum(1 for r in mcp if r.get("judgment", {}).get("correct"))
        da = dc / max(len(d), 1) * 100
        ma = mc / max(len(mcp), 1) * 100
        dt = sum(r.get("total_tokens", 0) for r in d)
        mt = sum(r.get("total_tokens", 0) for r in mcp)
        dco = sum(r.get("cost_usd", 0) for r in d)
        mco = sum(r.get("cost_usd", 0) for r in mcp)
        ratio = mt / max(dt, 1)
        lines.append(f"| {m} | **{da:.0f}%** ({dc}/{len(d)}) | {ma:.0f}% ({mc}/{len(mcp)}) | +{da-ma:.0f}pp | {dt:,} | {mt:,} | {ratio:.1f}x | ${dco:.2f} | ${mco:.2f} |")

    # By tier
    lines.append("")
    lines.append("## Results by Tier")
    lines.append("")
    tier_names = {1: "Simple", 2: "Semantic", 3: "Cross-Source"}
    for tier in [1, 2, 3]:
        d_tier = [r for r in results if r["approach"] == "dinobase" and r["tier"] == tier]
        m_tier = [r for r in results if r["approach"] == "raw_mcp" and r["tier"] == tier]
        dc = sum(1 for r in d_tier if r.get("judgment", {}).get("correct"))
        mc = sum(1 for r in m_tier if r.get("judgment", {}).get("correct"))
        da = dc / max(len(d_tier), 1) * 100
        ma = mc / max(len(m_tier), 1) * 100
        lines.append(f"**Tier {tier} ({tier_names[tier]})**: SQL {da:.0f}% vs MCP {ma:.0f}% (+{da-ma:.0f}pp)")
        lines.append("")

    # Why MCP fails
    lines.append("## Why Per-Source MCP Tools Fail")
    lines.append("")

    # Categorize MCP failures
    mcp_failures = [r for r in all_mcp if not r.get("judgment", {}).get("correct")]
    categories = defaultdict(int)
    for r in mcp_failures:
        answer = r.get("answer", "").lower()
        j = r.get("judgment", {}).get("explanation", "").lower()
        if "[max turns" in answer or "[tool use fail" in answer or "[api error" in answer:
            categories["Tool use / API failure"] += 1
        elif any(x in j for x in ["100x", "order of magnitude", "cents", "97x", "147x", "90x"]):
            categories["Cents-to-dollars conversion (no metadata)"] += 1
        elif any(x in j for x in ["pagination", "undercount", "partial data", "only saw"]):
            categories["Pagination (only sees 100 records)"] += 1
        elif r.get("tier") == 3 and any(x in j for x in ["cross", "correlat", "join", "cannot be"]):
            categories["Cannot join across sources"] += 1
        else:
            categories["Wrong answer / interpretation"] += 1

    lines.append("| Failure Category | Count | % of MCP Failures |")
    lines.append("|-----------------|-------|-------------------|")
    total_failures = sum(categories.values())
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {count} | {count/max(total_failures,1)*100:.0f}% |")
    lines.append("")

    # Semantic traps
    traps = defaultdict(lambda: {"sql_pass": 0, "sql_total": 0, "mcp_pass": 0, "mcp_total": 0})
    for r in results:
        trap = r.get("semantic_trap")
        if not trap:
            continue
        approach = r["approach"]
        correct = r.get("judgment", {}).get("correct", False)
        if approach == "dinobase":
            traps[trap]["sql_total"] += 1
            if correct:
                traps[trap]["sql_pass"] += 1
        else:
            traps[trap]["mcp_total"] += 1
            if correct:
                traps[trap]["mcp_pass"] += 1

    if traps:
        lines.append("## Semantic Trap Analysis")
        lines.append("")
        lines.append("| Trap | SQL Pass Rate | MCP Pass Rate | Gap |")
        lines.append("|------|-------------|--------------|-----|")
        for trap in sorted(traps.keys()):
            t = traps[trap]
            sr = t["sql_pass"] / max(t["sql_total"], 1) * 100
            mr = t["mcp_pass"] / max(t["mcp_total"], 1) * 100
            lines.append(f"| `{trap}` | {sr:.0f}% ({t['sql_pass']}/{t['sql_total']}) | {mr:.0f}% ({t['mcp_pass']}/{t['mcp_total']}) | +{sr-mr:.0f}pp |")
        lines.append("")

    # Methodology note
    lines.append("## Methodology")
    lines.append("")
    lines.append(f"- **Models**: {len(models)} ({', '.join(models)})")
    lines.append(f"- **Questions**: 15 RevOps questions (5 simple, 5 semantic, 5 cross-source)")
    lines.append(f"- **Approaches**: Dinobase (real product — QueryEngine + OpenAPI metadata) vs per-source MCP tools (in-memory API simulation)")
    lines.append(f"- **Judge**: Claude Haiku 4.5 (LLM-as-judge, different model from agents)")
    lines.append(f"- **Total cost**: ${sql_cost + mcp_cost:.2f}")
    lines.append(f"- **API**: All models via OpenRouter")
    lines.append("")

    return "\n".join(lines)


def main():
    results = load_results()
    if not results:
        print("No results found in benchmarks/results/")
        sys.exit(1)

    print(f"Loaded {len(results)} results from {len(set(r['model'] for r in results))} models")

    print("Generating charts...")
    has_charts = generate_charts(results)

    print("Generating report...")
    report = generate_report(results)

    report_path = RESULTS_DIR / "REPORT.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to {report_path}")

    # Print headline numbers to stdout
    all_sql = [r for r in results if r["approach"] == "dinobase"]
    all_mcp = [r for r in results if r["approach"] == "raw_mcp"]
    sql_correct = sum(1 for r in all_sql if r.get("judgment", {}).get("correct"))
    mcp_correct = sum(1 for r in all_mcp if r.get("judgment", {}).get("correct"))
    sql_tokens = sum(r.get("total_tokens", 0) for r in all_sql)
    mcp_tokens = sum(r.get("total_tokens", 0) for r in all_mcp)
    sql_cost = sum(r.get("cost_usd", 0) for r in all_sql)
    mcp_cost = sum(r.get("cost_usd", 0) for r in all_mcp)
    sql_cpc = sql_cost / max(sql_correct, 1)
    mcp_cpc = mcp_cost / max(mcp_correct, 1)

    print(f"\n{'='*50}")
    print(f"HEADLINE NUMBERS")
    print(f"{'='*50}")
    print(f"  Accuracy:       SQL {sql_correct}/{len(all_sql)} ({sql_correct/len(all_sql)*100:.0f}%) vs MCP {mcp_correct}/{len(all_mcp)} ({mcp_correct/len(all_mcp)*100:.0f}%)")
    print(f"  Accuracy gap:   +{sql_correct/len(all_sql)*100 - mcp_correct/len(all_mcp)*100:.0f} percentage points")
    print(f"  Token ratio:    {mcp_tokens/sql_tokens:.0f}x fewer tokens with SQL")
    print(f"  Cost ratio:     {mcp_cpc/sql_cpc:.0f}x cheaper per correct answer")
    print(f"  Total cost:     ${sql_cost + mcp_cost:.2f}")


if __name__ == "__main__":
    main()
