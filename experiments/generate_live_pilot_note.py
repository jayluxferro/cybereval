#!/usr/bin/env python3
"""Distill the latest CyberEval live-pilot artifact into a manuscript-facing note."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "experiments" / "results" / "real_results.json"
LATEST_SUMMARY_PATH = ROOT / "paper" / "artifacts" / "live_llm" / "latest_summary.json"
OUTPUT_PATH = ROOT / "paper" / "artifacts" / "live_llm" / "latest_note.json"
DIMENSION_ORDER = ["VK", "TI", "SC", "IR", "CG", "FA", "SA"]


def main() -> int:
    latest = json.loads(LATEST_SUMMARY_PATH.read_text(encoding="utf-8"))
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    artifact_dir = Path(latest["artifact_dir"])
    inputs = json.loads((artifact_dir / "inputs.json").read_text(encoding="utf-8"))

    ranking = latest["metrics"]["ranking"]
    if not ranking:
        raise RuntimeError("latest_summary.json contains no live-model ranking")
    leader = ranking[0]
    live_by_dimension = leader["by_dimension"]

    difficulty_histogram = {
        str(level): count
        for level, count in sorted(
            Counter(item["difficulty"] for item in inputs["sample"]).items()
        )
    }
    perfect_dimensions = [
        dim
        for dim in DIMENSION_ORDER
        if live_by_dimension.get(dim, {}).get("accuracy") == 1.0
    ]

    threshold = results["deployment_threshold"]
    simulated_frontier = results["model_ranking"][:2]
    frontier_below_threshold_dimensions = [
        dim
        for dim in DIMENSION_ORDER
        if all(
            results["model_scores"][model]["dimensions"][dim]["overall"] < threshold
            for model in simulated_frontier
        )
    ]
    saturated_below_threshold_dimensions = [
        dim for dim in frontier_below_threshold_dimensions if dim in perfect_dimensions
    ]

    note = {
        "artifact_dir": str(artifact_dir),
        "utc_timestamp": latest["utc_timestamp"],
        "baseline_commit": latest["baseline_commit"],
        "live_model": leader["model"],
        "sample_question_count": latest["metrics"]["sample_question_count"],
        "prompt_count": leader["count"],
        "correct": leader["correct"],
        "accuracy": leader["accuracy"],
        "mcq_accuracy": leader["mcq_accuracy"],
        "scenario_accuracy": leader["scenario_accuracy"],
        "scenario_gap_pp": leader["scenario_gap_pp"],
        "difficulty_histogram": difficulty_histogram,
        "sample_question_ids": [item["id"] for item in inputs["sample"]],
        "perfect_dimensions": perfect_dimensions,
        "all_dimensions_saturated": len(perfect_dimensions) == len(DIMENSION_ORDER),
        "deployment_threshold": threshold,
        "simulated_frontier": simulated_frontier,
        "frontier_below_threshold_dimensions": frontier_below_threshold_dimensions,
        "saturated_below_threshold_dimensions": saturated_below_threshold_dimensions,
        "interpretation": (
            "The refreshed live slice saturates all seven dimensions on a difficulty-2/3 sample, "
            "including dimensions that stay below the simulated deployment threshold, so it should "
            "be read as a provenance and ceiling-effect probe rather than as a discriminative live ranking."
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(note, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
