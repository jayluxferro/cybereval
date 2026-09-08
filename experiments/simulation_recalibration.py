"""Simulation recalibration check for the ARRAY revision (Reviewer 1 #4, Reviewer 3 #3).

The submitted paper reported a 39.5 percentage-point gap between deterministic
simulation predictions (calibrated on prior-generation benchmark trends, circa 2024)
and live measurements on current models, and interpreted it as capability
improvement. The reviewers correctly asked us to test whether the simulation
method itself, recalibrated on CURRENT data, reproduces the live measurements —
if it does, the gap is a calibration gap (stale priors), not simulation error.

Method:
1. Load the clean v2 live results (250-item balanced bank).
2. Pick a representative current model and estimate its per-dimension base
   accuracy and empirical difficulty decay from the live item-level responses.
3. Rebuild a simulation profile from those current estimates (noise = 0).
4. Run the existing simulate_model_responses() on the same 250-item bank.
5. Report the predicted vs observed scores (aggregate and per-dimension), plus
   the original prior-generation prediction for contrast.

Usage: python experiments/simulation_recalibration.py
Output: experiments/results/simulation_recalibration.json
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

from run_real_evaluation import simulate_model_responses, stable_model_seed  # noqa: E402

LIVE_PATH = ROOT / "experiments/results/live_mcq/v2_results.jsonl"
BANK_PATH = ROOT / "experiments/results/question_bank.json"
OUT_PATH = ROOT / "experiments/results/simulation_recalibration.json"

# Prior-generation profile used in the original simulation (from MODEL_PROFILES).
PRIOR_PROFILE = {
    "base": {"VK": 0.79, "TI": 0.76, "SC": 0.83, "IR": 0.70, "CG": 0.60, "FA": 0.72, "SA": 0.56},
    "diff_decay": 0.07,
    "format_mod": {"mcq": 0.04, "scenario": -0.06},
    "noise_std": 0.0,
}


def main():
    bank = json.loads(BANK_PATH.read_text())
    rows = [json.loads(l) for l in LIVE_PATH.read_text().splitlines() if l.strip()]
    assert len(rows) == 2000, f"expected 2000 rows, found {len(rows)}"

    # Representative current model for recalibration: the mid-tier DeepSeek-V4-Flash.
    ref_model = "DeepSeek-V4-Flash"
    ref_rows = [r for r in rows if r["model"] == ref_model and not r["raw_response"].startswith("ERROR:")]
    assert len(ref_rows) == 250

    # Per-dimension base accuracy for the reference model.
    dim_correct = defaultdict(int)
    dim_total = defaultdict(int)
    for r in ref_rows:
        dim_total[r["dimension"]] += 1
        if r["correct"]:
            dim_correct[r["dimension"]] += 1
    base = {d: dim_correct[d] / dim_total[d] for d in dim_total}

    # Empirical difficulty decay: linear slope of per-tier accuracy vs tier.
    tier_correct = defaultdict(int)
    tier_total = defaultdict(int)
    for r in ref_rows:
        tier_total[r["difficulty"]] += 1
        if r["correct"]:
            tier_correct[r["difficulty"]] += 1
    tiers = sorted(tier_total)
    accs = np.array([tier_correct[t] / tier_total[t] for t in tiers])
    slope, intercept = np.polyfit(tiers, accs, 1)
    diff_decay = float(-slope)  # accuracy drop per difficulty level

    recal_profile = {
        "base": base,
        "diff_decay": max(0.0, diff_decay),
        "format_mod": {"mcq": 0.0, "scenario": 0.0},
        "noise_std": 0.0,
    }

    # Simulate on the same bank with the prior and recalibrated profiles.
    qbank = [
        {"id": q["id"], "dimension": q["dimension"], "difficulty": q["difficulty"]}
        for q in bank
    ]
    prior_results = simulate_model_responses(qbank, "PriorGen", PRIOR_PROFILE, seed=42)
    recal_results = simulate_model_responses(qbank, "Recalibrated", recal_profile, seed=42)

    prior_score = sum(r["mcq_correct"] for r in prior_results) / len(prior_results)
    recal_score = sum(r["mcq_correct"] for r in recal_results) / len(recal_results)
    live_score = dim_correct and sum(dim_correct.values()) / sum(dim_total.values())

    # Live per-model scores for context.
    model_scores = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["raw_response"].startswith("ERROR:"):
            continue
        model_scores[r["model"]][1] += 1
        if r["correct"]:
            model_scores[r["model"]][0] += 1
    live_by_model = {m: c / t for m, (c, t) in model_scores.items()}

    out = {
        "reference_model": ref_model,
        "recalibrated_base": base,
        "recalibrated_diff_decay": diff_decay,
        "prior_profile_predicted_score": round(prior_score * 100, 1),
        "recalibrated_predicted_score": round(recal_score * 100, 1),
        "live_reference_model_score": round(live_score * 100, 1),
        "prior_gap_pp": round((live_score - prior_score) * 100, 1),
        "recalibrated_gap_pp": round((live_score - recal_score) * 100, 1),
        "live_scores_by_model": {m: round(s * 100, 1) for m, s in live_by_model.items()},
    }
    json.dump(out, OUT_PATH.open("w"), indent=2)

    print(f"reference model: {ref_model}")
    print(f"recalibrated base accuracies: {base}")
    print(f"empirical diff_decay: {diff_decay:.4f}")
    print(f"prior-generation profile predicts : {out['prior_profile_predicted_score']}%")
    print(f"recalibrated profile predicts    : {out['recalibrated_predicted_score']}%")
    print(f"live reference model score       : {out['live_reference_model_score']}%")
    print(f"gap before recalibration         : {out['prior_gap_pp']} pp")
    print(f"gap after recalibration          : {out['recalibrated_gap_pp']} pp")
    print(f"live scores by model: {out['live_scores_by_model']}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
