"""Regenerate paper figures from the clean v2 evaluation data (ARRAY revision).

Inputs:
- experiments/results/live_mcq/v2_results.jsonl  (2,000 rows, 8 models x 250 items)
- experiments/results/question_bank.json         (250 items, balanced positions)
- experiments/results/simulation_recalibration.json (from simulation_recalibration.py)

Outputs (paper/figures/):
- live_main_results.pdf/.png       accuracy bars + Wilson 95% CIs + 90% threshold
- live_difficulty.pdf/.png         per-tier accuracy lines, sample sizes annotated
- live_token_efficiency.pdf/.png   accuracy vs tokens per question
- live_sim_vs_live.pdf/.png        prior sim vs recalibrated sim vs live bars
- live_mcnemar.pdf/.png            pairwise exact McNemar significance matrix

Usage: python experiments/make_revision_figures.py
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments/results"
FIG = ROOT / "paper/figures"
LIVE = DATA / "live_mcq/v2_results.jsonl"

MODEL_ORDER = [
    "Claude-Sonnet-4.6", "Gemma-4-31B", "DeepSeek-V4-Flash", "Nemotron-Super-120B",
    "DeepSeek-V4-Pro", "Kimi-K2.6", "Qwen-3.6-35B", "Qwen-3.5-9B",
]
# Compact axis labels (full names appear in the tables).
SHORT = {
    "Claude-Sonnet-4.6": "Claude",
    "Gemma-4-31B": "Gemma",
    "DeepSeek-V4-Flash": "DS-Flash",
    "Nemotron-Super-120B": "Nemotron",
    "DeepSeek-V4-Pro": "DS-Pro",
    "Kimi-K2.6": "Kimi",
    "Qwen-3.6-35B": "Qwen-35B",
    "Qwen-3.5-9B": "Qwen-9B",
}
# Per-model annotation offsets (points) for the token-efficiency scatter,
# hand-placed so no label collides with another point or label.
TOKEN_OFFSETS = {
    "Claude-Sonnet-4.6": (-44, 7),
    "Gemma-4-31B": (-4, -14),
    "DeepSeek-V4-Flash": (16, 5),
    "DeepSeek-V4-Pro": (-38, 7),
    "Nemotron-Super-120B": (12, 8),
    "Kimi-K2.6": (10, 8),
    "Qwen-3.6-35B": (10, -14),
    "Qwen-3.5-9B": (-40, -13),
}
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]


def wilson(k, n, z=1.96):
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z / denom * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return center - half, center + half


def load():
    rows = [json.loads(l) for l in LIVE.read_text().splitlines() if l.strip()]
    assert len(rows) == 2000, f"expected 2000 rows, got {len(rows)}"
    bank = json.loads((DATA / "question_bank.json").read_text())
    assert len(bank) == 250
    per_model = defaultdict(lambda: {"correct": 0, "total": 0, "tokens": 0,
                                     "by_tier": defaultdict(lambda: [0, 0])})
    for r in rows:
        m = per_model[r["model"]]
        m["total"] += 1
        m["tokens"] += r.get("tokens", 0)
        m["by_tier"][r["difficulty"]][1] += 1
        if r["correct"]:
            m["correct"] += 1
            m["by_tier"][r["difficulty"]][0] += 1
    return rows, bank, per_model


def fig_main(per_model):
    models = [m for m in MODEL_ORDER if m in per_model]
    accs = [per_model[m]["correct"] / per_model[m]["total"] * 100 for m in models]
    cis = [wilson(per_model[m]["correct"], per_model[m]["total"]) for m in models]
    errs = [[(accs[i] - cis[i][0] * 100), (cis[i][1] * 100 - accs[i])] for i in range(len(models))]

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = range(len(models))
    bars = ax.bar(x, accs, yerr=([e[0] for e in errs], [e[1] for e in errs]),
                  capsize=3, color=COLORS[:len(models)], edgecolor="black", linewidth=0.4)
    ax.axhline(90, color="black", linestyle="--", linewidth=1)
    ax.text(0.2, 90.6, "illustrative floor-test threshold (90%)",
            fontsize=8, ha="left", va="bottom")
    ax.set_xticks(list(x))
    ax.set_xticklabels([SHORT[m] for m in models], rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Live MCQ accuracy on 250 cybersecurity questions (Wilson 95% CI)")
    for i, b in enumerate(bars):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5,
                f"{accs[i]:.1f}", ha="center", fontsize=7)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"live_main_results.{ext}", dpi=150 if ext == "png" else None)
    plt.close(fig)


def fig_difficulty(per_model):
    tiers = [1, 2, 3, 4, 5]
    bank = json.loads((DATA / "question_bank.json").read_text())
    tier_n = {t: sum(1 for q in bank if q["difficulty"] == t) for t in tiers}
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for i, m in enumerate(MODEL_ORDER):
        if m not in per_model:
            continue
        accs = [per_model[m]["by_tier"][t][0] / per_model[m]["by_tier"][t][1] * 100
                if per_model[m]["by_tier"][t][1] else float("nan") for t in tiers]
        ax.plot(tiers, accs, marker="o", markersize=4, linewidth=1.4,
                color=COLORS[i], label=SHORT[m])
    ax.set_xticks(tiers)
    ax.set_xticklabels([f"T{t}\n(n={tier_n[t]})" for t in tiers], fontsize=8)
    ax.set_xlabel("Difficulty tier (sample size)")
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Model accuracy by difficulty tier (250-item balanced bank)")
    ax.legend(fontsize=7, ncol=2, loc="lower left", framealpha=0.9)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"live_difficulty.{ext}", dpi=150 if ext == "png" else None)
    plt.close(fig)


def fig_tokens(per_model):
    models = [m for m in MODEL_ORDER if m in per_model]
    accs = [per_model[m]["correct"] / per_model[m]["total"] * 100 for m in models]
    tpq = [per_model[m]["tokens"] / per_model[m]["total"] for m in models]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for i, m in enumerate(models):
        ax.scatter(tpq[i], accs[i], s=60, color=COLORS[i], edgecolor="black",
                   linewidth=0.4, label=SHORT[m])
    ax.legend(fontsize=7, ncol=4, loc="lower right", framealpha=0.9,
              handletextpad=0.3, columnspacing=0.8)
    ax.set_xlabel("Tokens per question (provider-reported total)")
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(65, 106)
    ax.set_title("Accuracy vs. token consumption")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"live_token_efficiency.{ext}", dpi=150 if ext == "png" else None)
    plt.close(fig)


def fig_sim_vs_live():
    recal = json.loads((DATA / "simulation_recalibration.json").read_text())
    labels = ["Prior-generation\nsimulation (2024 calib.)", "Recalibrated\nsimulation",
              "Live ceiling\n(current models)"]
    vals = [recal["prior_profile_predicted_score"], recal["recalibrated_predicted_score"],
            recal["live_reference_model_score"]]
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    bars = ax.bar(labels, vals, color=["#999999", "#2ca02c", "#1f77b4"],
                  edgecolor="black", linewidth=0.4)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.1f}", ha="center", fontsize=9)
    ax.set_ylabel("Predicted / observed top score (%)")
    ax.set_ylim(0, 110)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_title("Simulation recalibration: gap closes when calibrated on current data",
                 pad=14)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"live_sim_vs_live.{ext}", dpi=150 if ext == "png" else None)
    plt.close(fig)


def fig_mcnemar(rows):
    from scipy.stats import binomtest  # scipy verified available in this env
    models = [m for m in MODEL_ORDER
              if any(r["model"] == m for r in rows)]
    n = len(models)
    # per-model item correctness vectors over 250 items
    item = {m: {} for m in models}
    for r in rows:
        item[r["model"]][r["question_idx"]] = int(r["correct"])
    idxs = sorted(item[models[0]].keys())
    mat = [[1.0] * n for _ in range(n)]
    for i, a in enumerate(models):
        va = [item[a][q] for q in idxs]
        for j, b in enumerate(models):
            if i == j:
                continue
            vb = [item[b][q] for q in idxs]
            bb = sum(1 for x, y in zip(va, vb) if x and not y)
            cc = sum(1 for x, y in zip(va, vb) if not x and y)
            p = binomtest(min(bb, cc), bb + cc, 0.5).pvalue if bb + cc else 1.0
            mat[i][j] = p
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    im = ax.imshow([[min(m, 0.05) for m in row] for row in mat],
                   cmap="RdYlGn_r", vmin=0, vmax=0.05)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    short = [SHORT[m] for m in models]
    ax.set_xticklabels(short, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(short, fontsize=8)
    for i in range(n):
        for j in range(n):
            p = mat[i][j]
            if i != j:
                # dark cells (small p) get white text, light cells get black
                ax.text(j, i, "<0.0018" if p < 0.0018 else f"{p:.3f}",
                        ha="center", va="center", fontsize=7,
                        color="white" if p < 0.02 else "black")
    ax.set_title("Exact McNemar p-values (paired items)\n"
                 "row vs column; <0.0018 = significant after Bonferroni", pad=10)
    fig.colorbar(im, ax=ax, label="p (capped at 0.05)")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"live_mcnemar.{ext}", dpi=150 if ext == "png" else None)
    plt.close(fig)


def main():
    rows, bank, per_model = load()
    print("models:", {m: per_model[m]["correct"] for m in MODEL_ORDER if m in per_model})
    fig_main(per_model)
    fig_difficulty(per_model)
    fig_tokens(per_model)
    if (DATA / "simulation_recalibration.json").exists():
        fig_sim_vs_live()
    fig_mcnemar(rows)
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
