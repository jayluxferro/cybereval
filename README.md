# CyberEval — Reproducibility Repository

Companion data-and-code repository for the paper *Measuring the Ceiling: Evidence That Easy-to-Medium Cybersecurity MCQ Benchmarks Have Saturated for Current-Generation LLMs*. The manuscript is under review and is submitted directly to the journal; it is not hosted here. This repository exists so that every number in the paper can be independently re-derived.

## What's here

- `experiments/results/` — the measurement data:
  - `question_bank.json` — the 250-item bank (7 dimensions, tiers 1–5, balanced answer positions 62/63/63/62) plus `bank_balance_provenance.json`
  - `round2_validated/` — the validated single-day re-measurement (2,000 calls, 2026-10-01): complete answer and reasoning content, finish reasons, served-model identifiers, per-call UTC timestamps (`full_run.jsonl`); the adjudication docket (`docket.jsonl`); the validated answer set with per-row four-extractor values (`validated_answers.json`); per-item IRT/discrimination statistics (`item_stats.json`); the simulation recalibration (`simulation_recalibration.json`); the computed summary (`summary.txt`)
  - `live_mcq/` — the original 2026-09-08 protocol trace and the superseded 50-token-budget provenance run
- `experiments/` — the scripts that reproduce the run, every analysis, and every figure:
  - `run_full_recapture.py` — the validated run (idempotent; 4 in-place retries with 2/4/8 s backoff)
  - `analyze_validated.py` — re-derives all scores, CIs, McNemar tests, tier statistics, correlations, hard-tail splits, and the docket/answer-set/item-stats artifacts
  - `simulation_recalibration_validated.py` — reproduces the calibration experiment
  - `make_round2_figures.py` — regenerates all five data figures
  - earlier-revision scripts retained as provenance (`run_live_mcq_v2.py`, `analyze_revision_v2.py`, `balance_bank.py`, …)
- `cybereval-array-release-<date>.zip` — the versioned release (same data + scripts, self-contained; see `RELEASE_NOTES.md` inside for the protocol, dates, served models, and the pre-registered adjudication rubric)

## Quick validation

```bash
# from the repo (or extract the release zip and run from its root):
python3 experiments/analyze_validated.py          # all statistics in the paper
python3 experiments/simulation_recalibration_validated.py   # 58.8 / 93.6 / 98.0
CYBEREVAL_FIG_DIR=figs python3 experiments/make_round2_figures.py  # all figures
```

Only the raw model inference cannot be bit-reproduced (temperature 0.0 does not guarantee repeatability of hosted outputs); all post-inference processing is deterministic, which is why the complete traces are released.

## Validated headline results (2026-10-01 re-measurement, validated answers)

| Model | Score | Wilson 95% CI |
|-------|-------|---------------|
| Claude-Sonnet-4.6 | 100.0% (250/250) | [98.5, 100.0] |
| Gemma-4-31B | 99.6% (249/250) | [97.8, 99.9] |
| Qwen-3.6-35B | 99.6% (249/250) | [97.8, 99.9] |
| DeepSeek-V4-Pro | 99.2% (248/250) | [97.1, 99.8] |
| Nemotron-Super-120B | 98.8% (247/250) | [96.5, 99.6] |
| Kimi-K2.6 | 98.4% (246/250) | [96.0, 99.4] |
| DeepSeek-V4-Flash | 98.0% (245/250) | [95.4, 99.1] |
| Qwen-3.5-9B | 97.6% (244/250) | [94.9, 98.9] |

- Paired exact McNemar tests over the 28 model pairs: one nominally significant at α = 0.05 (Claude-Sonnet-4.6 vs. Qwen-3.5-9B, p = 0.031); none at the Bonferroni-corrected level.
- Hard tail (50 tier-4/5 items): scores span 90.0–100%; on the 40 new hard items: 87.5–100%; on the original 210: 99.0–100%.
- 22 incorrect responses in 2,000: 21 generation-budget exhaustions (`finish_reason = length`) and one committed wrong letter.
- An earlier protocol run's apparent stragglers (Kimi 89.6%, Nemotron 73.2% recorded) were answer-extraction artifacts: re-parsing that run's own stored text yields 88.0% for Nemotron, and the validated re-measurement yields 98.4%/98.8%.
