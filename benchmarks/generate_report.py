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
    except ImportError:
        print("  matplotlib not installed — skipping charts. pip install matplotlib")
        return False

    CHARTS_DIR.mkdir(exist_ok=True)

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
        dc = sum(1 for r in d if r.get("judgment", {}).get("correct"))
        mc = sum(1 for r in mcp if r.get("judgment", {}).get("correct"))
        dco = sum(r.get("cost_usd", 0) for r in d)
        mco = sum(r.get("cost_usd", 0) for r in mcp)
        stats[m] = {
            "sql_acc": dc / max(len(d), 1) * 100,
            "mcp_acc": mc / max(len(mcp), 1) * 100,
            "sql_cpc": dco / max(dc, 1) * 1000,
            "mcp_cpc": mco / max(mc, 1) * 1000,
            "sql_latency": sum(r.get("latency_ms", 0) for r in d) / max(len(d), 1) / 1000,
            "mcp_latency": sum(r.get("latency_ms", 0) for r in mcp) / max(len(mcp), 1) / 1000,
        }

    bar_width = 0.35
    colors = {"sql": "#2563eb", "mcp": "#dc2626"}

    # --- Chart 1: Accuracy ---
    order = sorted(models, key=lambda m: stats[m]["sql_acc"])
    lbls = [model_labels.get(m, m) for m in order]
    xpos = range(len(order))
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

    # --- Chart 2: Cost per correct answer ---
    order = sorted(models, key=lambda m: stats[m]["sql_cpc"])
    lbls = [model_labels.get(m, m) for m in order]
    xpos = range(len(order))
    fig, ax = plt.subplots(figsize=(14, 6))
    sql_cpc = [stats[m]["sql_cpc"] for m in order]
    mcp_cpc = [stats[m]["mcp_cpc"] for m in order]
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

    # --- Chart 3: Average latency per question ---
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

    all_sql = [r for r in results if r["approach"] == "dinobase"]
    all_mcp = [r for r in results if r["approach"] == "raw_mcp"]
    sql_correct = sum(1 for r in all_sql if r.get("judgment", {}).get("correct"))
    mcp_correct = sum(1 for r in all_mcp if r.get("judgment", {}).get("correct"))
    sql_acc = sql_correct / max(len(all_sql), 1) * 100
    mcp_acc = mcp_correct / max(len(all_mcp), 1) * 100
    sql_cost = sum(r.get("cost_usd", 0) for r in all_sql)
    mcp_cost = sum(r.get("cost_usd", 0) for r in all_mcp)
    sql_cost_per_correct = sql_cost / max(sql_correct, 1)
    mcp_cost_per_correct = mcp_cost / max(mcp_correct, 1)
    cost_ratio = mcp_cost_per_correct / max(sql_cost_per_correct, 0.0001)
    accuracy_gap = sql_acc - mcp_acc
    sql_avg_latency = sum(r.get("latency_ms", 0) for r in all_sql) / max(len(all_sql), 1) / 1000
    mcp_avg_latency = sum(r.get("latency_ms", 0) for r in all_mcp) / max(len(all_mcp), 1) / 1000
    latency_ratio = mcp_avg_latency / max(sql_avg_latency, 0.001)
    models = sorted(set(r["model"] for r in results))

    lines.append("# Dinobase Benchmark Results")
    lines.append("")
    lines.append(f"**{len(models)} models** · **15 RevOps questions** · HubSpot CRM + Stripe billing")
    lines.append("")

    lines.append("## Results")
    lines.append("")
    lines.append(f"| Metric | Dinobase (SQL) | Per-Source MCP | Difference |")
    lines.append(f"|--------|---------------|---------------|------------|")
    lines.append(f"| **Accuracy** | **{sql_acc:.0f}%** ({sql_correct}/{len(all_sql)}) | {mcp_acc:.0f}% ({mcp_correct}/{len(all_mcp)}) | **+{accuracy_gap:.0f} percentage points** |")
    lines.append(f"| **Avg latency per question** | {sql_avg_latency:.1f}s | {mcp_avg_latency:.1f}s | **{latency_ratio:.1f}x faster** |")
    lines.append(f"| **Cost per correct answer** | ${sql_cost_per_correct:.3f} | ${mcp_cost_per_correct:.3f} | **{cost_ratio:.0f}x cheaper** |")
    lines.append("")
    lines.append(f"*Cost per correct answer = total API cost / questions answered correctly.*")
    lines.append("")

    # Charts
    if (CHARTS_DIR / "accuracy.png").exists():
        lines.append("## Charts")
        lines.append("")
        lines.append("### Accuracy")
        lines.append("![Accuracy](charts/accuracy.png)")
        lines.append("")
        lines.append("### Latency")
        lines.append("![Latency](charts/latency.png)")
        lines.append("")
        lines.append("### Cost per Correct Answer")
        lines.append("![Cost](charts/cost_per_correct.png)")
        lines.append("")

    # Per-model table
    lines.append("## Per-Model Results")
    lines.append("")
    lines.append("| Model | SQL Accuracy | MCP Accuracy | Gap | SQL Latency | MCP Latency | SQL $/Correct | MCP $/Correct |")
    lines.append("|-------|-------------|-------------|-----|------------|------------|--------------|--------------|")
    model_display = {
        "claude-haiku-4.5": "Claude Haiku 4.5",
        "claude-opus-4.6": "Claude Opus 4.6",
        "claude-sonnet-4.6": "Claude Sonnet 4.6",
        "deepseek-v3.2": "DeepSeek V3.2",
        "gemini-3-flash": "Gemini 3 Flash",
        "gemini-3.1-pro": "Gemini 3.1 Pro",
        "glm-5-turbo": "GLM-5 Turbo",
        "gpt-5.4": "GPT 5.4",
        "kimi-k2.5": "Kimi K2.5",
        "minimax-m2.7": "MiniMax M2.7",
        "qwen-3.5-27b": "Qwen 3.5 27B",
    }
    # Sort by SQL accuracy descending
    def sort_key(m):
        d = [r for r in results if r["model"] == m and r["approach"] == "dinobase"]
        dc = sum(1 for r in d if r.get("judgment", {}).get("correct"))
        return dc / max(len(d), 1)

    for m in sorted(models, key=sort_key, reverse=True):
        d = [r for r in results if r["model"] == m and r["approach"] == "dinobase"]
        mcp = [r for r in results if r["model"] == m and r["approach"] == "raw_mcp"]
        dc = sum(1 for r in d if r.get("judgment", {}).get("correct"))
        mc = sum(1 for r in mcp if r.get("judgment", {}).get("correct"))
        da = dc / max(len(d), 1) * 100
        ma = mc / max(len(mcp), 1) * 100
        dco = sum(r.get("cost_usd", 0) for r in d)
        mco = sum(r.get("cost_usd", 0) for r in mcp)
        dl = sum(r.get("latency_ms", 0) for r in d) / max(len(d), 1) / 1000
        ml = sum(r.get("latency_ms", 0) for r in mcp) / max(len(mcp), 1) / 1000
        sql_cpc = dco / max(dc, 1)
        mcp_cpc = mco / max(mc, 1)
        label = model_display.get(m, m)
        lines.append(f"| {label} | **{da:.0f}%** ({dc}/{len(d)}) | {ma:.0f}% ({mc}/{len(mcp)}) | +{da-ma:.0f}pp | {dl:.0f}s | {ml:.0f}s | ${sql_cpc:.3f} | ${mcp_cpc:.3f} |")

    # By tier
    lines.append("")
    lines.append("## Results by Tier")
    lines.append("")
    lines.append("| Tier | SQL Accuracy | MCP Accuracy | Gap |")
    lines.append("|------|-------------|-------------|-----|")
    tier_names = {1: "Tier 1 — Simple (single-source)", 2: "Tier 2 — Semantic (domain knowledge)", 3: "Tier 3 — Cross-Source (joins required)"}
    for tier in [1, 2, 3]:
        d_tier = [r for r in results if r["approach"] == "dinobase" and r["tier"] == tier]
        m_tier = [r for r in results if r["approach"] == "raw_mcp" and r["tier"] == tier]
        dc = sum(1 for r in d_tier if r.get("judgment", {}).get("correct"))
        mc = sum(1 for r in m_tier if r.get("judgment", {}).get("correct"))
        da = dc / max(len(d_tier), 1) * 100
        ma = mc / max(len(m_tier), 1) * 100
        lines.append(f"| {tier_names[tier]} | {da:.0f}% | {ma:.0f}% | +{da-ma:.0f}pp |")

    # Why MCP fails
    lines.append("")
    lines.append("## Why Per-Source MCP Tools Fail")
    lines.append("")

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

    # Methodology
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(f"- **Models**: {len(models)} ({', '.join(models)})")
    lines.append(f"- **Questions**: 15 RevOps questions — 5 simple (single-source), 5 semantic (domain knowledge required), 5 cross-source (joins required)")
    lines.append(f"- **Same for both**: same LLM, same data, same questions, max turns 15, temperature 0")
    lines.append(f"- **Scoring**: deterministic for ~60% of questions (regex + tolerance checks), LLM-as-judge (Claude Haiku 4.5) for remainder")
    lines.append(f"- **Total benchmark cost**: ${sql_cost + mcp_cost:.2f} via OpenRouter")
    lines.append(f"- **Full methodology**: [README.md](../README.md)")
    lines.append("")

    return "\n".join(lines)


def main():
    results = load_results()
    if not results:
        print("No results found in benchmarks/results/")
        sys.exit(1)

    print(f"Loaded {len(results)} results from {len(set(r['model'] for r in results))} models")

    print("Generating charts...")
    generate_charts(results)

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
    sql_cost = sum(r.get("cost_usd", 0) for r in all_sql)
    mcp_cost = sum(r.get("cost_usd", 0) for r in all_mcp)
    sql_cpc = sql_cost / max(sql_correct, 1)
    mcp_cpc = mcp_cost / max(mcp_correct, 1)
    sql_lat = sum(r.get("latency_ms", 0) for r in all_sql) / max(len(all_sql), 1) / 1000
    mcp_lat = sum(r.get("latency_ms", 0) for r in all_mcp) / max(len(all_mcp), 1) / 1000

    print(f"\n{'='*50}")
    print(f"HEADLINE NUMBERS")
    print(f"{'='*50}")
    print(f"  Accuracy:    SQL {sql_correct}/{len(all_sql)} ({sql_correct/len(all_sql)*100:.0f}%) vs MCP {mcp_correct}/{len(all_mcp)} ({mcp_correct/len(all_mcp)*100:.0f}%) — +{sql_correct/len(all_sql)*100 - mcp_correct/len(all_mcp)*100:.0f}pp")
    print(f"  Latency:     SQL {sql_lat:.1f}s vs MCP {mcp_lat:.1f}s — {mcp_lat/sql_lat:.1f}x faster")
    print(f"  Cost/correct: SQL ${sql_cpc:.3f} vs MCP ${mcp_cpc:.3f} — {mcp_cpc/sql_cpc:.0f}x cheaper")
    print(f"  Total cost:  ${sql_cost + mcp_cost:.2f}")


if __name__ == "__main__":
    main()
