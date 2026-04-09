import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "experiments" / "results" / "real_results.json"
MANUSCRIPT_PATH = ROOT / "paper" / "main.tex"
PDF_PATH = ROOT / "paper" / "main.pdf"
LATEST_LIVE_SUMMARY_PATH = (
    ROOT / "paper" / "artifacts" / "live_llm" / "latest_summary.json"
)
LATEST_LIVE_NOTE_PATH = ROOT / "paper" / "artifacts" / "live_llm" / "latest_note.json"


def _distance(results: dict, model_a: str, model_b: str) -> float:
    dims = list(results["dimensions"].keys())
    scores = results["model_scores"]
    return math.sqrt(
        sum(
            (
                scores[model_a]["dimensions"][dim]["overall"]
                - scores[model_b]["dimensions"][dim]["overall"]
            )
            ** 2
            for dim in dims
        )
    )


def _oxford_join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def test_manuscript_tracks_key_scores_profiles_and_figures():
    results = json.loads(RESULTS_PATH.read_text())
    manuscript = MANUSCRIPT_PATH.read_text()

    ranking = results["model_ranking"]
    leader = ranking[0]
    runner_up = ranking[1]
    leader_score = results["model_scores"][leader]["aggregate"] * 100
    runner_up_score = results["model_scores"][runner_up]["aggregate"] * 100
    average_gap = results["avg_format_gap"] * 100
    frontier_distance = _distance(results, leader, runner_up)
    weakest_distance = _distance(results, leader, ranking[-1])

    dims = list(results["dimensions"].keys())
    coverage = [
        dim
        for dim in dims
        if results["model_scores"][leader]["dimensions"][dim]["overall"]
        >= results["deployment_threshold"]
    ]

    assert f"{leader_score:.1f}\\%" in manuscript
    assert f"{runner_up_score:.1f}\\%" in manuscript
    assert f"{average_gap:.1f} points" in manuscript
    assert f"$D={frontier_distance:.3f}$" in manuscript
    assert f"$D={weakest_distance:.3f}$" in manuscript
    assert "four of the seven dimensions" in manuscript
    assert ", ".join(coverage) in manuscript

    for figure_ref in [
        "figures/aggregate_ranking.pdf",
        "figures/radar_profiles.pdf",
        "figures/profile_distance_heatmap.pdf",
        "figures/irt_distribution.pdf",
        "figures/dimension_boxplot.pdf",
    ]:
        assert figure_ref in manuscript


def test_manuscript_tracks_role_weighted_margins():
    results = json.loads(RESULTS_PATH.read_text())
    manuscript = MANUSCRIPT_PATH.read_text()

    appsec = results["role_scores"]["appsec_engineer"]
    appsec_ranked = sorted(appsec, key=appsec.get, reverse=True)
    leader = appsec_ranked[0]
    runner_up = appsec_ranked[1]
    margin = (appsec[leader] - appsec[runner_up]) * 100
    leader_risk = results["role_risks"]["appsec_engineer"][leader]
    runner_up_risk = results["role_risks"]["appsec_engineer"][runner_up]

    grc = results["role_scores"]["grc_analyst"]
    grc_ranked = sorted(grc, key=grc.get, reverse=True)
    grc_margin = (grc[grc_ranked[0]] - grc[grc_ranked[1]]) * 100
    grc_leader_risk = results["role_risks"]["grc_analyst"][grc_ranked[0]]
    grc_runner_up_risk = results["role_risks"]["grc_analyst"][grc_ranked[1]]

    assert f"{margin:.1f} points" in manuscript
    assert f"{runner_up_risk:.4f} to {leader_risk:.4f}" in manuscript
    assert f"{grc_margin:.1f} points" in manuscript
    assert f"{grc_leader_risk:.4f} versus {grc_runner_up_risk:.4f}" in manuscript


def test_manuscript_tracks_latest_live_pilot_summary():
    manuscript = MANUSCRIPT_PATH.read_text()
    latest = json.loads(LATEST_LIVE_SUMMARY_PATH.read_text())
    note = json.loads(LATEST_LIVE_NOTE_PATH.read_text())
    ranking = latest["metrics"]["ranking"][0]

    model = ranking["model"]
    overall = ranking["accuracy"] * 100
    mcq = ranking["mcq_accuracy"] * 100
    scenario = ranking["scenario_accuracy"] * 100
    gap = ranking["scenario_gap_pp"]
    correct = ranking["correct"]
    total = ranking["count"]
    difficulty_two = note["difficulty_histogram"].get("2", 0)
    difficulty_three = note["difficulty_histogram"].get("3", 0)
    below_threshold_dims = _oxford_join(note["saturated_below_threshold_dimensions"])

    assert model in manuscript
    assert f"{correct}/{total}" in manuscript
    assert f"{overall:.1f}\\%" in manuscript
    assert f"{mcq:.1f}\\%" in manuscript
    assert f"{scenario:.1f}\\%" in manuscript
    assert f"{gap:.1f}-point" in manuscript
    assert "all seven dimensions" in manuscript
    assert (
        f"{difficulty_two} difficulty-2 items and {difficulty_three} difficulty-3 items"
        in manuscript
    )
    assert below_threshold_dims in manuscript


def test_manuscript_avoids_internal_validation_prose():
    manuscript = MANUSCRIPT_PATH.read_text()
    banned_fragments = [
        "real_results.json",
        "pytest",
        "uv run",
        "experiments/results/",
        "paper/figures/",
        "Reproducibility and Artifact Checklist",
        "Publication artifact provenance",
    ]
    for fragment in banned_fragments:
        assert fragment not in manuscript


def test_pdf_stays_in_publication_window():
    output = subprocess.run(
        ["pdfinfo", str(PDF_PATH)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pages_line = next(line for line in output.splitlines() if line.startswith("Pages:"))
    pages = int(pages_line.split(":", 1)[1].strip())
    assert 20 <= pages <= 40
