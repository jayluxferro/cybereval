#!/usr/bin/env python3
"""Simulation recalibration on the VALIDATED dataset (ARRAY round 2).

Reproduces experiments/results/round2_validated/simulation_recalibration.json:
prior-generation calibration profile prediction (58.8%) vs. the same simulation
mechanism recalibrated on current validated measurements (93.6%) vs. the live
reference-model score (98.0%, DeepSeek-V4-Flash, validated answers).

Method: identical to experiments/simulation_recalibration.py, but anchored to
the validated single-day re-run (round2_validated/full_run.jsonl) with
adjudicated answers instead of the 2026-09-08 protocol run's recorded parses.

Usage: python experiments/simulation_recalibration_validated.py
Output: experiments/results/round2_validated/simulation_recalibration.json
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

from run_real_evaluation import simulate_model_responses  # noqa: E402

def _locate(name):
    candidates = [
        ROOT / "experiments/results" / name,
        ROOT / "data" / name,
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"{name} not found; checked {candidates}")

FULL_RUN = _locate("round2_validated/full_run.jsonl")
VALIDATED = _locate("round2_validated/validated_answers.json")
BANK = _locate("question_bank.json")
OUT = FULL_RUN.parent / "simulation_recalibration.json"

# Prior-generation profile from the original framework's headline comparison
# (Claude-3.5-Sonnet-parameterized tier with deterministic noise).
PRIOR_PROFILE = {
    "base": {"VK": 0.79, "TI": 0.76, "SC": 0.83, "IR": 0.70, "CG": 0.60, "FA": 0.72, "SA": 0.56},
    "diff_decay": 0.07,
    "format_mod": {"mcq": 0.04, "scenario": -0.06},
    "noise_std": 0.0,
}


def main():
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in FULL_RUN.read_text(encoding="utf-8").splitlines() if l.strip()]
    best = {}
    for r in rows:
        if not r.get("raw_full", "").startswith("ERROR:"):
            best[(r["model"], r["question_idx"])] = r
    rows = list(best.values())
    assert len(rows) == 2000, f"expected 2000 rows, got {len(rows)}"
    val = json.loads(VALIDATED.read_text(encoding="utf-8"))

    ref_model = "DeepSeek-V4-Flash"
    ref_rows = [r for r in rows if r["model"] == ref_model]
    assert len(ref_rows) == 250

    dim_correct = defaultdict(int)
    dim_total = defaultdict(int)
    for r in ref_rows:
        dim_total[r["dimension"]] += 1
        if val[f"{ref_model}|{r['question_idx']}"]["adjudicated"] == r["correct_idx"]:
            dim_correct[r["dimension"]] += 1
    base = {d: dim_correct[d] / dim_total[d] for d in dim_total}

    tier_correct = defaultdict(int)
    tier_total = defaultdict(int)
    for r in ref_rows:
        tier_total[r["difficulty"]] += 1
        if val[f"{ref_model}|{r['question_idx']}"]["adjudicated"] == r["correct_idx"]:
            tier_correct[r["difficulty"]] += 1
    tiers = sorted(tier_total)
    accs = np.array([tier_correct[t] / tier_total[t] for t in tiers])
    slope, _ = np.polyfit(tiers, accs, 1)
    diff_decay = float(-slope)

    recal_profile = {
        "base": base,
        "diff_decay": max(0.0, diff_decay),
        "format_mod": {"mcq": 0.0, "scenario": 0.0},
        "noise_std": 0.0,
    }

    qbank = [{"id": q["id"], "dimension": q["dimension"], "difficulty": q["difficulty"]}
             for q in bank]
    prior_results = simulate_model_responses(qbank, "PriorGen", PRIOR_PROFILE, seed=42)
    recal_results = simulate_model_responses(qbank, "Recalibrated", recal_profile, seed=42)

    prior_score = 100 * sum(r["mcq_correct"] for r in prior_results) / len(prior_results)
    recal_score = 100 * sum(r["mcq_correct"] for r in recal_results) / len(recal_results)
    live_ref = 100 * sum(dim_correct.values()) / sum(dim_total.values())

    out = {
        "prior_profile_predicted_score": round(prior_score, 2),
        "recalibrated_predicted_score": round(recal_score, 2),
        "live_reference_model_score": round(live_ref, 2),
        "source": "round2_validated full_run.jsonl, adjudicated answers, DeepSeek-V4-Flash reference",
        "prior_profile": PRIOR_PROFILE,
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
