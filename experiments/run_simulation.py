#!/usr/bin/env python3
"""CyberEval Experimental Simulation."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json, sys, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.framework import CyberEvalFramework, DIMENSIONS
from src.evaluator import SecurityEvaluator
from src.profiler import CompetencyProfiler

np.random.seed(42)
random.seed(42)

OUTPUT_DIR = Path(__file__).parent.parent / "paper" / "figures"
RESULTS_DIR = Path(__file__).parent.parent / "experiments" / "results"
for d in [OUTPUT_DIR, RESULTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

print("CyberEval Experimental Simulation")
print("=" * 50)

# Run evaluation
framework = CyberEvalFramework()
items = framework.generate_items(n_per_dim=100)
evaluator = SecurityEvaluator()
profiler = CompetencyProfiler()

models = list(evaluator.MODEL_PROFILES.keys())
all_results = {}

print("\nEvaluating models...")
for model in models:
    scores = evaluator.evaluate(items, model)
    agg = profiler.aggregate_score(scores)
    profile = profiler.create_profile(scores)
    gaps = profiler.compute_gaps(scores)
    all_results[model] = {"aggregate": agg, "dimensions": {s.dimension: s.score for s in scores}, "gaps": len(gaps)}
    print(f"  {model:20s}: Aggregate={agg:.1%}, Gaps={len(gaps)}")

print("\nGenerating figures...")

# Figure 1: Radar chart for top 4 models
fig, axes = plt.subplots(1, 2, figsize=(14, 6), subplot_kw=dict(polar=True))
dims = list(DIMENSIONS.keys())
dim_names = list(DIMENSIONS.values())
angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
angles += angles[:1]

top_models = models[:4]
colors_radar = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12"]

for idx, ax in enumerate(axes):
    model_group = top_models[:2] if idx == 0 else top_models[2:4] if len(top_models) > 2 else []
    for i, model in enumerate(model_group):
        values = [all_results[model]["dimensions"].get(d, 0) for d in dims]
        values += values[:1]
        ax.plot(angles, values, "-o", linewidth=2, label=model, color=colors_radar[idx*2+i], markersize=4)
        ax.fill(angles, values, alpha=0.1, color=colors_radar[idx*2+i])
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dim_names, fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_title(f"Competency Profile ({', '.join(model_group)})", fontsize=11, pad=20)
    ax.legend(fontsize=9, loc="upper right", bbox_to_anchor=(1.3, 1.1))
    ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "radar_profiles.pdf", dpi=300, bbox_inches="tight")
plt.savefig(OUTPUT_DIR / "radar_profiles.png", dpi=150, bbox_inches="tight")
plt.close()
print("  [+] radar_profiles.pdf")

# Figure 2: Dimension heatmap for all models
fig, ax = plt.subplots(1, 1, figsize=(12, 7))
data = np.array([[all_results[m]["dimensions"].get(d, 0) for d in dims] for m in models])
im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=0.25, vmax=0.85)
ax.set_xticks(range(len(dims)))
ax.set_xticklabels([DIMENSIONS[d] for d in dims], fontsize=9, rotation=30, ha="right")
ax.set_yticks(range(len(models)))
ax.set_yticklabels(models, fontsize=9)
for i in range(len(models)):
    for j in range(len(dims)):
        color = "white" if data[i,j] > 0.65 or data[i,j] < 0.35 else "black"
        ax.text(j, i, f"{data[i,j]:.1%}", ha="center", va="center", fontsize=8, color=color)
plt.colorbar(im, ax=ax, label="Score")
ax.set_title("CyberEval: Security Competency Heatmap", fontsize=13)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "competency_heatmap.pdf", dpi=300, bbox_inches="tight")
plt.savefig(OUTPUT_DIR / "competency_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print("  [+] competency_heatmap.pdf")

# Figure 3: Aggregate comparison
fig, ax = plt.subplots(1, 1, figsize=(10, 6))
agg_scores = [all_results[m]["aggregate"] for m in models]
colors = ["#2ecc71" if s == max(agg_scores) else "#3498db" for s in agg_scores]
bars = ax.barh(models, agg_scores, color=colors, edgecolor="white", height=0.6)
ax.set_xlabel("Aggregate Score")
ax.set_title("CyberEval: Model Rankings", fontsize=13)
ax.set_xlim(0.3, 0.85)
ax.grid(True, axis="x", alpha=0.3)
for bar, s in zip(bars, agg_scores):
    ax.text(s + 0.005, bar.get_y() + bar.get_height()/2, f"{s:.1%}", va="center", fontsize=9)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "aggregate_ranking.pdf", dpi=300, bbox_inches="tight")
plt.savefig(OUTPUT_DIR / "aggregate_ranking.png", dpi=150, bbox_inches="tight")
plt.close()
print("  [+] aggregate_ranking.pdf")

with open(RESULTS_DIR / "experimental_results.json", "w") as f:
    json.dump(all_results, f, indent=2)
print("  [+] experimental_results.json")

print("\n" + "=" * 50)
print("All outputs generated!")
