# CyberEval

**Role-aware multi-dimensional evaluation of LLM security competence**

CyberEval is a reproducible evaluation framework for analyzing LLM suitability
across seven security dimensions:

1. Vulnerability Knowledge (VK)
2. Threat Intelligence (TI)
3. Secure Coding (SC)
4. Incident Response (IR)
5. Compliance & Governance (CG)
6. Forensic Analysis (FA)
7. Security Architecture (SA)

## What this artifact does

The current release is a **framework artifact plus deterministic simulation
study**, not a live API leaderboard. It provides:

- a 210-item seed question bank
- paired MCQ/scenario evaluation channels
- role-weighted suitability scoring for SOC, AppSec, GRC, and architecture workflows
- aligned paper figures and result JSONs
- full response traces for auditability

## Quick start

From the repo root:

```bash
# From the repo root
python experiments/run_simulation.py
```

This regenerates:

- `experiments/results/real_results.json`
- `experiments/results/experimental_results.json`
- `experiments/results/question_bank.json`
- `experiments/results/response_traces.json`
- paper figures in `paper/figures/`

## Current deterministic simulation snapshot

- **Top aggregate profile:** Claude-3.5-Sonnet — **60.5%**
- **Runner-up:** GPT-4o — **56.9%**
- **Average MCQ-to-scenario gap:** **11.2 percentage points**
- **Strongest mean dimension:** Secure Coding — **58.5%**
- **Weakest mean dimensions:** Compliance & Governance — **31.3%**, Security Architecture — **22.7%**

### Role-weighted leaders

- **SOC analyst:** Claude-3.5-Sonnet — **63.2%**
- **AppSec engineer:** Claude-3.5-Sonnet — **65.3%**
- **GRC analyst:** Claude-3.5-Sonnet — **50.9%**
- **Security architect:** Claude-3.5-Sonnet — **52.5%**

## Paper

The LNCS paper lives at:

- `paper/main.tex`

It is written to match the generated artifacts and explicitly documents the
current limitations of the benchmark:

- no live API execution yet
- no standalone free-text scenario corpus yet
- difficulty imbalance in the seed bank
- model profiles calibrated from public benchmark trends rather than direct measurements

## License

MIT License
