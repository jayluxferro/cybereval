"""Consistency checks between the revised manuscript and the v2 evaluation data.

Rewritten for the ARRAY revision: the manuscript's live results must match the
clean 250-item v2 run (balanced answer positions), and the bibliography must be
free of placeholder entries.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT_PATH = ROOT / "paper" / "main.tex"
PDF_PATH = ROOT / "paper" / "main.pdf"
BIB_PATH = ROOT / "paper" / "references.bib"
LIVE_PATH = ROOT / "experiments" / "results" / "live_mcq" / "v2_results.jsonl"
BANK_PATH = ROOT / "experiments" / "results" / "question_bank.json"

MODEL_LABELS = [
    "Kimi-K2.6",
    "Claude-Sonnet-4.6",
    "Gemma-4-31B",
    "DeepSeek-V4-Pro",
    "Qwen-3.5-9B",
    "DeepSeek-V4-Flash",
    "Qwen-3.6-35B",
    "Nemotron-Super-120B",
]


def _manuscript():
    return MANUSCRIPT_PATH.read_text()


def _live_rows():
    return [json.loads(l) for l in LIVE_PATH.read_text().splitlines() if l.strip()]


def _bank():
    return json.loads(BANK_PATH.read_text())


def test_live_dataset_is_complete():
    rows = _live_rows()
    assert len(rows) == 2000, f"expected 2000 rows, got {len(rows)}"
    per_model = {}
    for r in rows:
        per_model.setdefault(r["model"], 0)
        per_model[r["model"]] += 1
    assert per_model == {m: 250 for m in MODEL_LABELS}, per_model
    assert all(r["ts_utc"] for r in rows), "missing timestamps"


def test_bank_is_balanced_and_sized():
    bank = _bank()
    assert len(bank) == 250
    positions = [q["correct"] for q in bank]
    counts = sorted(positions.count(i) for i in range(4))
    assert counts == [62, 62, 63, 63], counts


def test_manuscript_reports_live_scores():
    ms = _manuscript()
    rows = _live_rows()
    per_model = {}
    for r in rows:
        per_model.setdefault(r["model"], [0, 0])
        per_model[r["model"]][1] += 1
        if r["correct"]:
            per_model[r["model"]][0] += 1
    for m in MODEL_LABELS:
        acc = per_model[m][0] / per_model[m][1] * 100
        # Table rows are formatted "99.2 & 248/250"; prose uses "98.4\%".
        assert (f"{acc:.1f} & {per_model[m][0]}/250" in ms
                or f"{acc:.1f}\\%" in ms), f"missing {acc:.1f}% for {m}"


def test_manuscript_reports_bank_composition():
    ms = _manuscript()
    assert "250-item" in ms or "250 cybersecurity questions" in ms
    assert "62, 62, 63" in ms
    assert "39 at tier 4" in ms
    assert "11 at tier 5" in ms


def test_manuscript_uses_paired_statistics():
    ms = _manuscript()
    assert "McNemar" in ms
    # CI-overlap must not be presented as a significance test.
    assert "overlapping confidence intervals, meaning" not in ms
    assert "statistically indistinguishable at this sample size" not in ms


def test_manuscript_has_no_position_bias_typo():
    ms = _manuscript()
    assert "easyto" not in ms


def test_bibliography_has_no_placeholder_entries():
    bib = BIB_PATH.read_text()
    # The three reviewer-flagged fabricated IDs ended in ".12345".
    assert re.search(r"arXiv[: ]*\d{4}\.\d{5}\b", bib) is not None  # normal IDs exist
    for bad in ["2407.12345", "2406.12345", "2405.12345"]:
        assert bad not in bib, f"placeholder arXiv ID still present: {bad}"
    # All \cite keys in the manuscript must exist in the bibliography.
    cited = set()
    for group in re.findall(r"\\cite\{([^}]+)\}", _manuscript()):
        cited.update(k.strip() for k in group.split(","))
    for key in cited:
        assert f"@article{{{key}," in bib or f"@inproceedings{{{key}," in bib or \
               f"@techreport{{{key}," in bib or f"@misc{{{key}," in bib, \
               f"cited key missing from bib: {key}"


def test_manuscript_avoids_internal_validation_prose():
    ms = _manuscript()
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
        assert fragment not in ms


def test_pdf_stays_in_publication_window():
    output = subprocess.run(
        ["pdfinfo", str(PDF_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )
    pages = int(re.search(r"Pages:\s+(\d+)", output.stdout).group(1))
    assert pages <= 30, f"PDF grew to {pages} pages"
