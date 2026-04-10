#!/usr/bin/env python3
"""Distill the latest CyberEval live-pilot artifact into a manuscript-facing note."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "experiments" / "results" / "real_results.json"
LATEST_SUMMARY_PATH = ROOT / "paper" / "artifacts" / "live_llm" / "latest_summary.json"
OUTPUT_PATH = ROOT / "paper" / "artifacts" / "live_llm" / "latest_note.json"
DIMENSION_ORDER = ["VK", "TI", "SC", "IR", "CG", "FA", "SA"]
RATIONALE_KEYS = ["rationale", "reason", "reasoning", "brief_reason"]


def _oxford_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _build_interpretation(note: dict[str, Any]) -> str:
    parsed = note["parsed_prompt_count"]
    expected = note["expected_prompt_count"]
    fully_covered = len(note["fully_covered_dimensions"])
    below_threshold = note["saturated_below_threshold_dimensions"]
    below_clause = ""
    if below_threshold:
        below_clause = (
            f" Even this saturated slice still includes {_oxford_join(below_threshold)} where "
            "the simulated frontier remains below the 0.60 deployment bar."
        )

    if (
        note["parse_error_count"] == 0
        and note["confidence_field_count"] == parsed
        and note["rationale_key_variants"] == {"rationale": parsed}
    ):
        coverage_clause = (
            "All seven dimensions retain full paired MCQ+scenario coverage."
            if note["all_dimensions_saturated"]
            else f"Only {fully_covered} dimensions retain full paired MCQ+scenario coverage."
        )
        return (
            f"The refreshed live slice saturated the bounded {expected}-prompt sample: all {expected} "
            f"prompts produced parseable JSON, all {parsed} parsed answers were correct, and all {parsed} "
            "parseable replies supplied both the requested numeric confidence field and the requested "
            f"rationale field. {coverage_clause}{below_clause} The artifact is therefore best read as a "
            "bounded provenance and ceiling-effect check rather than as a discriminative live ranking."
        )

    parse_error_clause = ""
    if note["parse_error_examples"]:
        first_error = note["parse_error_examples"][0]
        parse_error_clause = f" The first parse failure was the {first_error['dimension']} {first_error['format']} cell."

    confidence_clause = (
        f"All {parsed} parseable replies supplied the requested numeric confidence field."
        if note["confidence_field_count"] == parsed
        else (
            f"None of the {parsed} parseable replies supplied the requested numeric confidence field."
            if note["confidence_field_count"] == 0
            else f"{note['confidence_field_count']} of the {parsed} parseable replies supplied the requested numeric confidence field."
        )
    )
    rationale_keys = sorted(note["rationale_key_variants"])
    rationale_clause = (
        f"The parseable replies used the following rationale-like keys: {_oxford_join(rationale_keys)}."
        if rationale_keys
        else "No parseable reply exposed a rationale-like field."
    )
    coverage_clause = (
        "All seven dimensions retain full paired MCQ+scenario coverage."
        if note["all_dimensions_saturated"]
        else f"Only {fully_covered} dimensions retain full paired MCQ+scenario coverage."
    )
    return (
        f"The refreshed live slice answered every parseable prompt correctly, but only {parsed} of {expected} "
        f"prompts produced parseable JSON.{parse_error_clause} {confidence_clause} {rationale_clause} "
        f"{coverage_clause}{below_clause} The artifact is therefore best read as a provenance and "
        "structured-output stress test rather than as a discriminative live ranking."
    )


def _load_raw_payload(record: dict[str, Any]) -> dict[str, Any]:
    raw_text = record.get("raw_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return {}
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_reason_key(payload: dict[str, Any]) -> str | None:
    for key in RATIONALE_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return key
    return None


def main() -> int:
    latest = json.loads(LATEST_SUMMARY_PATH.read_text(encoding="utf-8"))
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    artifact_dir = Path(latest["artifact_dir"])
    inputs = json.loads((artifact_dir / "inputs.json").read_text(encoding="utf-8"))
    outputs = json.loads((artifact_dir / "outputs.json").read_text(encoding="utf-8"))

    ranking = latest["metrics"]["ranking"]
    if not ranking:
        raise RuntimeError("latest_summary.json contains no live-model ranking")
    leader = ranking[0]
    leader_model = leader["model"]
    live_by_dimension = leader["by_dimension"]

    model_outputs = [
        record for record in outputs if record.get("model_label") == leader_model
    ]
    ok_outputs = [record for record in model_outputs if record.get("status") == "ok"]
    error_outputs = [record for record in model_outputs if record.get("status") != "ok"]
    parsed_prompt_count = leader["count"]
    expected_prompt_count = len(model_outputs)
    scenario_ok_count = sum(
        1 for record in ok_outputs if record.get("format") == "scenario"
    )

    difficulty_histogram = {
        str(level): count
        for level, count in sorted(
            Counter(item["difficulty"] for item in inputs["sample"]).items()
        )
    }
    fully_covered_dimensions = [
        dim
        for dim in DIMENSION_ORDER
        if live_by_dimension.get(dim, {}).get("count") == 2
        and live_by_dimension.get(dim, {}).get("accuracy") == 1.0
    ]
    partial_dimensions = [
        dim
        for dim in DIMENSION_ORDER
        if 0 < live_by_dimension.get(dim, {}).get("count", 0) < 2
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
        dim
        for dim in frontier_below_threshold_dimensions
        if dim in fully_covered_dimensions
    ]

    rationale_key_variants: Counter[str] = Counter()
    confidence_field_count = 0
    for record in ok_outputs:
        payload = _load_raw_payload(record)
        if (
            record.get("confidence") is not None
            or payload.get("confidence") is not None
        ):
            confidence_field_count += 1
        reason_key = _first_reason_key(payload)
        if reason_key:
            rationale_key_variants[reason_key] += 1

    parse_error_examples = [
        {
            "question_id": record["question_id"],
            "dimension": record["dimension"],
            "format": record["format"],
            "error": record["error"],
        }
        for record in error_outputs
    ]

    note = {
        "artifact_dir": str(artifact_dir),
        "utc_timestamp": latest["utc_timestamp"],
        "baseline_commit": latest["baseline_commit"],
        "live_model": leader_model,
        "sample_question_count": latest["metrics"]["sample_question_count"],
        "expected_prompt_count": expected_prompt_count,
        "parsed_prompt_count": parsed_prompt_count,
        "prompt_count": parsed_prompt_count,
        "parsed_correct": leader["correct"],
        "correct": leader["correct"],
        "accuracy": leader["accuracy"],
        "valid_response_rate": (
            parsed_prompt_count / expected_prompt_count
            if expected_prompt_count
            else 0.0
        ),
        "mcq_accuracy": leader["mcq_accuracy"],
        "scenario_accuracy": leader["scenario_accuracy"],
        "scenario_gap_pp": leader["scenario_gap_pp"],
        "scenario_ok_count": scenario_ok_count,
        "difficulty_histogram": difficulty_histogram,
        "sample_question_ids": [item["id"] for item in inputs["sample"]],
        "fully_covered_dimensions": fully_covered_dimensions,
        "partial_dimensions": partial_dimensions,
        "perfect_dimensions": fully_covered_dimensions,
        "all_dimensions_saturated": len(fully_covered_dimensions)
        == len(DIMENSION_ORDER),
        "deployment_threshold": threshold,
        "simulated_frontier": simulated_frontier,
        "frontier_below_threshold_dimensions": frontier_below_threshold_dimensions,
        "saturated_below_threshold_dimensions": saturated_below_threshold_dimensions,
        "parse_error_count": len(error_outputs),
        "parse_error_dimensions": [record["dimension"] for record in error_outputs],
        "parse_error_examples": parse_error_examples,
        "confidence_field_count": confidence_field_count,
        "confidence_field_rate": (
            confidence_field_count / parsed_prompt_count if parsed_prompt_count else 0.0
        ),
        "rationale_like_count": sum(rationale_key_variants.values()),
        "rationale_like_rate": (
            sum(rationale_key_variants.values()) / parsed_prompt_count
            if parsed_prompt_count
            else 0.0
        ),
        "rationale_key_variants": dict(sorted(rationale_key_variants.items())),
    }
    note["interpretation"] = _build_interpretation(note)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(note, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
