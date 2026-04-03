import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "experiments" / "results" / "real_results.json"
MANUSCRIPT_PATH = ROOT / "paper" / "main.tex"
PDF_PATH = ROOT / "paper" / "main.pdf"


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
