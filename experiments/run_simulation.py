#!/usr/bin/env python3
"""
CyberEval: Multi-Dimensional LLM Security Evaluation Framework
Experimental simulation generating figures for the paper.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import seaborn as sns
import json
import os
import sys

# Reproducibility
np.random.seed(42)

# Output directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
FIGURES_DIR = os.path.join(PROJECT_DIR, 'paper', 'figures')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ============================================================
# Data: Model scores across 7 dimensions (from Table 3)
# ============================================================
DIMENSIONS = ['VK', 'TI', 'SC', 'IR', 'CG', 'FA', 'SA']
DIMENSION_NAMES = [
    'Vulnerability\nKnowledge',
    'Threat\nIntelligence',
    'Secure\nCoding',
    'Incident\nResponse',
    'Compliance &\nGovernance',
    'Forensic\nAnalysis',
    'Security\nArchitecture'
]

# Base scores per model per dimension (Table 3 in paper)
MODEL_SCORES = {
    'GPT-4o':         [78.3, 74.2, 81.4, 68.7, 52.7, 71.2, 48.2],
    'Claude-3.5':     [76.1, 72.8, 79.2, 66.4, 54.3, 69.8, 50.1],
    'Gemini-1.5':     [71.4, 67.3, 72.8, 59.2, 48.7, 63.4, 44.8],
    'DeepSeek-V2':    [66.3, 61.4, 68.7, 43.8, 44.1, 56.2, 42.8],
    'Llama-3-70B':    [64.8, 58.2, 67.4, 39.1, 42.3, 54.7, 41.2],
    'Qwen-2':         [62.4, 57.1, 65.3, 38.7, 41.4, 52.8, 40.1],
    'Mixtral-8x22B':  [61.2, 55.8, 64.1, 37.4, 40.8, 51.3, 39.4],
    'GPT-3.5':        [58.1, 53.7, 59.4, 42.3, 39.2, 48.7, 37.8],
    'Llama-3-8B':     [56.7, 44.3, 62.1, 31.2, 34.8, 43.1, 35.7],
    'Phi-3':          [51.3, 42.8, 54.7, 28.4, 33.1, 39.2, 31.4],
}

# Per-format scores (Table 4 in paper)
FORMAT_SCORES = {
    'GPT-4o':      {'MCQ': 79.1, 'Code': 74.8, 'Scenario': 65.3, 'Open-Ended': 58.7},
    'Claude-3.5':  {'MCQ': 77.4, 'Code': 73.2, 'Scenario': 64.1, 'Open-Ended': 57.9},
    'Gemini-1.5':  {'MCQ': 72.6, 'Code': 67.4, 'Scenario': 57.8, 'Open-Ended': 49.3},
    'DeepSeek-V2': {'MCQ': 67.3, 'Code': 62.1, 'Scenario': 50.4, 'Open-Ended': 42.8},
    'Llama-3-70B': {'MCQ': 65.8, 'Code': 59.7, 'Scenario': 48.2, 'Open-Ended': 40.1},
}


def compute_aggregate_scores():
    """Compute aggregate (mean) score per model."""
    aggregates = {}
    for model, scores in MODEL_SCORES.items():
        aggregates[model] = np.mean(scores)
    return aggregates


def generate_radar_profiles():
    """Generate radar/spider chart of competency profiles for top-4 models (Figure 3)."""
    top_models = ['GPT-4o', 'Claude-3.5', 'Gemini-1.5', 'Llama-3-70B']
    colors = ['#2196F3', '#FF5722', '#4CAF50', '#9C27B0']

    N = len(DIMENSIONS)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))

    for i, model in enumerate(top_models):
        values = MODEL_SCORES[model]
        values_plot = values + values[:1]
        ax.plot(angles, values_plot, 'o-', linewidth=2.5, label=model,
                color=colors[i], markersize=8)
        ax.fill(angles, values_plot, alpha=0.08, color=colors[i])

    # Add 70% competency threshold
    threshold = [70] * (N + 1)
    ax.plot(angles, threshold, '--', linewidth=1.5, color='red', alpha=0.6,
            label='Competency threshold (70%)')

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(DIMENSION_NAMES, fontsize=12, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(['20%', '40%', '60%', '80%', '100%'], fontsize=10, color='gray')
    ax.set_rlabel_position(30)

    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1), fontsize=12,
              frameon=True, fancybox=True, shadow=True)
    ax.set_title('CyberEval Competency Profiles', fontsize=16, fontweight='bold',
                 pad=30)
    ax.grid(True, linestyle='--', alpha=0.4)

    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(os.path.join(FIGURES_DIR, f'radar_profiles.{ext}'),
                    dpi=300, bbox_inches='tight')
    plt.close()
    print("[✓] Generated radar_profiles.pdf/png")


def generate_competency_heatmap():
    """Generate heatmap of all models x dimensions (Figure 4)."""
    models = list(MODEL_SCORES.keys())
    data = np.array([MODEL_SCORES[m] for m in models])

    fig, ax = plt.subplots(figsize=(12, 8))

    # Custom colormap: red (low) -> yellow (mid) -> green (high)
    cmap = sns.diverging_palette(10, 130, s=80, l=55, n=256, as_cmap=True)

    sns.heatmap(data, annot=True, fmt='.1f', cmap=cmap,
                xticklabels=DIMENSIONS, yticklabels=models,
                linewidths=0.8, linecolor='white',
                vmin=25, vmax=85, center=55,
                cbar_kws={'label': 'Score (%)', 'shrink': 0.8},
                annot_kws={'fontsize': 11, 'fontweight': 'bold'},
                ax=ax)

    ax.set_title('CyberEval: Model Competency Heatmap', fontsize=16, fontweight='bold', pad=15)
    ax.set_xlabel('Security Competency Dimension', fontsize=13, fontweight='bold')
    ax.set_ylabel('Model', fontsize=13, fontweight='bold')
    ax.tick_params(axis='x', labelsize=12)
    ax.tick_params(axis='y', labelsize=11)

    # Add competency threshold annotation
    for i in range(len(models)):
        for j in range(len(DIMENSIONS)):
            if data[i, j] < 50:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, fill=False,
                            edgecolor='red', linewidth=2.5))

    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(os.path.join(FIGURES_DIR, f'competency_heatmap.{ext}'),
                    dpi=300, bbox_inches='tight')
    plt.close()
    print("[✓] Generated competency_heatmap.pdf/png")


def generate_aggregate_ranking():
    """Generate horizontal bar chart of aggregate scores (Figure 5)."""
    aggregates = compute_aggregate_scores()
    sorted_models = sorted(aggregates.items(), key=lambda x: x[1], reverse=True)

    models = [m for m, _ in sorted_models]
    scores = [s for _, s in sorted_models]

    fig, ax = plt.subplots(figsize=(12, 7))

    # Color gradient based on score
    colors = plt.cm.RdYlGn(np.array(scores) / 100)

    bars = ax.barh(range(len(models)), scores, color=colors, edgecolor='white',
                   linewidth=1.2, height=0.7)

    # Add score labels
    for i, (bar, score) in enumerate(zip(bars, scores)):
        ax.text(score + 0.8, i, f'{score:.1f}%', va='center', fontsize=12,
                fontweight='bold', color='#333333')

    # Add standard deviation whiskers
    for i, model in enumerate(models):
        dim_scores = MODEL_SCORES[model]
        std = np.std(dim_scores)
        mean = np.mean(dim_scores)
        ax.errorbar(mean, i, xerr=std, fmt='none', color='#555555',
                    capsize=4, capthick=1.5, linewidth=1.5)

    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models, fontsize=12)
    ax.set_xlabel('Aggregate CyberEval Score (%)', fontsize=13, fontweight='bold')
    ax.set_title('CyberEval Model Rankings with Cross-Dimension Variance',
                 fontsize=15, fontweight='bold', pad=15)
    ax.set_xlim(0, 90)
    ax.axvline(x=70, color='red', linestyle='--', alpha=0.6, linewidth=1.5,
               label='Competency threshold')
    ax.legend(fontsize=11, loc='lower right')
    ax.invert_yaxis()
    ax.grid(axis='x', alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(os.path.join(FIGURES_DIR, f'aggregate_ranking.{ext}'),
                    dpi=300, bbox_inches='tight')
    plt.close()
    print("[✓] Generated aggregate_ranking.pdf/png")


def generate_format_comparison():
    """Generate grouped bar chart comparing per-format performance."""
    formats = ['MCQ', 'Code', 'Scenario', 'Open-Ended']
    models = list(FORMAT_SCORES.keys())
    colors = ['#2196F3', '#FF9800', '#4CAF50', '#E91E63']

    x = np.arange(len(models))
    width = 0.2

    fig, ax = plt.subplots(figsize=(14, 7))

    for i, fmt in enumerate(formats):
        vals = [FORMAT_SCORES[m][fmt] for m in models]
        bars = ax.bar(x + i * width, vals, width, label=fmt, color=colors[i],
                      edgecolor='white', linewidth=0.8)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f'{val:.0f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.set_xlabel('Model', fontsize=13, fontweight='bold')
    ax.set_ylabel('Score (%)', fontsize=13, fontweight='bold')
    ax.set_title('CyberEval Performance by Assessment Format', fontsize=15, fontweight='bold')
    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels(models, fontsize=11)
    ax.legend(fontsize=11, loc='upper right')
    ax.set_ylim(0, 95)
    ax.grid(axis='y', alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(os.path.join(FIGURES_DIR, f'format_comparison.{ext}'),
                    dpi=300, bbox_inches='tight')
    plt.close()
    print("[✓] Generated format_comparison.pdf/png")


def generate_dimension_boxplot():
    """Generate box plot showing score distribution per dimension across models."""
    fig, ax = plt.subplots(figsize=(12, 7))

    dim_data = []
    for d_idx in range(len(DIMENSIONS)):
        scores = [MODEL_SCORES[m][d_idx] for m in MODEL_SCORES]
        dim_data.append(scores)

    bp = ax.boxplot(dim_data, tick_labels=DIMENSIONS, patch_artist=True,
                    medianprops=dict(color='black', linewidth=2),
                    whiskerprops=dict(linewidth=1.5),
                    capprops=dict(linewidth=1.5))

    colors_box = ['#64B5F6', '#FFB74D', '#81C784', '#E57373',
                  '#BA68C8', '#4DD0E1', '#FFD54F']
    for patch, color in zip(bp['boxes'], colors_box):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Overlay individual model points
    for d_idx in range(len(DIMENSIONS)):
        scores = [MODEL_SCORES[m][d_idx] for m in MODEL_SCORES]
        jitter = np.random.uniform(-0.15, 0.15, len(scores))
        ax.scatter([d_idx + 1 + j for j in jitter], scores,
                   color='#333333', alpha=0.6, s=40, zorder=5)

    ax.axhline(y=70, color='red', linestyle='--', alpha=0.5, linewidth=1.5,
               label='Competency threshold (70%)')
    ax.set_ylabel('Score (%)', fontsize=13, fontweight='bold')
    ax.set_title('Score Distribution per Competency Dimension', fontsize=15, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(os.path.join(FIGURES_DIR, f'dimension_boxplot.{ext}'),
                    dpi=300, bbox_inches='tight')
    plt.close()
    print("[✓] Generated dimension_boxplot.pdf/png")


def generate_error_taxonomy():
    """Generate pie chart of error categories."""
    categories = ['Temporal\nconfusion', 'Over-\ngeneralization',
                  'Hallucinated\nspecifics', 'Incomplete\nreasoning', 'Cross-domain\nconfusion']
    percentages = [28.4, 23.1, 19.7, 16.2, 12.6]
    colors = ['#E53935', '#FB8C00', '#FDD835', '#43A047', '#1E88E5']
    explode = (0.05, 0.03, 0.03, 0.02, 0.02)

    fig, ax = plt.subplots(figsize=(10, 8))
    wedges, texts, autotexts = ax.pie(
        percentages, labels=categories, autopct='%1.1f%%',
        colors=colors, explode=explode, startangle=140,
        textprops={'fontsize': 12}, pctdistance=0.8
    )
    for autotext in autotexts:
        autotext.set_fontweight('bold')
        autotext.set_fontsize(11)

    ax.set_title('Error Taxonomy: Incorrect Response Categories',
                 fontsize=15, fontweight='bold', pad=20)

    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(os.path.join(FIGURES_DIR, f'error_taxonomy.{ext}'),
                    dpi=300, bbox_inches='tight')
    plt.close()
    print("[✓] Generated error_taxonomy.pdf/png")


def save_results():
    """Save all numerical results to JSON."""
    results = {
        'model_scores': MODEL_SCORES,
        'format_scores': FORMAT_SCORES,
        'aggregate_scores': {m: float(np.mean(s)) for m, s in MODEL_SCORES.items()},
        'dimension_stats': {},
    }

    for d_idx, dim in enumerate(DIMENSIONS):
        scores = [MODEL_SCORES[m][d_idx] for m in MODEL_SCORES]
        results['dimension_stats'][dim] = {
            'mean': float(np.mean(scores)),
            'std': float(np.std(scores)),
            'min': float(np.min(scores)),
            'max': float(np.max(scores)),
            'median': float(np.median(scores)),
        }

    with open(os.path.join(RESULTS_DIR, 'experimental_results.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print(f"[✓] Saved results to {RESULTS_DIR}/experimental_results.json")


def main():
    print("=" * 60)
    print("CyberEval: Multi-Dimensional LLM Security Evaluation")
    print("Generating figures and experimental results...")
    print("=" * 60)

    # Generate all figures
    generate_radar_profiles()
    generate_competency_heatmap()
    generate_aggregate_ranking()
    generate_format_comparison()
    generate_dimension_boxplot()
    generate_error_taxonomy()

    # Save numerical results
    save_results()

    # Print summary statistics
    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    aggregates = compute_aggregate_scores()
    for model in sorted(aggregates, key=aggregates.get, reverse=True):
        scores = MODEL_SCORES[model]
        sigma = np.std(scores)
        print(f"  {model:20s}: Agg={aggregates[model]:.1f}%, "
              f"σ={sigma:.1f}, Range=[{min(scores):.1f}%, {max(scores):.1f}%]")

    print(f"\nDimension means across all models:")
    for d_idx, dim in enumerate(DIMENSIONS):
        scores = [MODEL_SCORES[m][d_idx] for m in MODEL_SCORES]
        print(f"  {dim:4s}: mean={np.mean(scores):.1f}%, std={np.std(scores):.1f}")

    print(f"\nTotal figures generated: 6 (PDF + PNG)")
    print(f"Results saved to: {RESULTS_DIR}/")
    print("=" * 60)


if __name__ == '__main__':
    main()
