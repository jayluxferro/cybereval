# CyberEval

**Measuring the Ceiling: Evidence That Easy-to-Medium Cybersecurity MCQ Benchmarks Have Saturated for Current-Generation LLMs**

CyberEval evaluates LLM cybersecurity competence across 7 dimensions using a 250-item MCQ question bank with balanced answer positions. It provides reproducible, live-API evidence that easy-to-medium cybersecurity MCQs have saturated for current-generation models, and documents how answer-extraction artifacts can masquerade as capability gaps on reasoning-mode models.

## Validated Live Evaluation Results (2026-10-01 re-measurement)

8 models evaluated across 250 questions, validated answers (adjudication docket in `experiments/results/round2_validated/`):

| Model | Score | Provider |
|-------|-------|----------|
| Claude-Sonnet-4.6 | 100.0% | Anthropic (via OpenRouter) |
| Gemma-4-31B | 99.6% | Google (via DoubleWordAI) |
| Qwen-3.6-35B | 99.6% | Alibaba (via DoubleWordAI) |
| DeepSeek-V4-Pro | 99.2% | DeepSeek (via DoubleWordAI) |
| Nemotron-Super-120B | 98.8% | NVIDIA (via DoubleWordAI) |
| Kimi-K2.6 | 98.4% | Moonshot AI (via DoubleWordAI) |
| DeepSeek-V4-Flash | 98.0% | DeepSeek (via DoubleWordAI) |
| Qwen-3.5-9B | 97.6% | Alibaba (via DoubleWordAI) |

**Key findings:** all 8 models score at or above 97.6% (top-to-bottom spread 2.4 points); no model pair is significant after Bonferroni correction (1 of 28 pairs nominally significant at α=0.05). On the 40 new hard items (tiers 4–5) scores span 87.5–100% — discrimination survives only on the hard tail. An earlier protocol run's apparent stragglers (Kimi 89.6%, Nemotron 73.2%) were answer-extraction artifacts: the strict first-letter parser mis-read reasoning-mode responses, as the re-parsed original traces and the validated re-run show (Section 5.3 of the paper). The easy-to-medium MCQ format no longer discriminates between competent models — it can only flag clearly unsuitable ones (floor test).

## Reproducibility release

`cybereval-array-release-<date>.zip` (built by `scripts/package_release.sh`, notes in `scripts/RELEASE_NOTES.md`) contains the 250-item bank, the complete validated trace (2,000 calls with timestamps and served-model identifiers), the original protocol trace as provenance, the adjudication docket, and the scripts that reproduce every number and figure in the paper.

## 7 Security Dimensions

1. Vulnerability Knowledge (VK)
2. Threat Intelligence (TI)
3. Secure Coding (SC)
4. Incident Response (IR)
5. Compliance & Governance (CG)
6. Forensic Analysis (FA)
7. Security Architecture (SA)

## Repository Structure

```
paper/
  main.tex          — Elsevier Array paper (elsarticle, 57 refs)
  main.pdf          — compiled paper
  figures/          — data figures regenerated from the validated run (main results, difficulty tiers, McNemar, sim vs live, token efficiency)
experiments/
  run_live_mcq.py   — live evaluation runner (8 models × 210 questions)
  run_real_evaluation.py — original simulation runner (210-item question bank source)
  run_simulation.py — paper figure generator (simulation-based)
  results/
    live_mcq/results.jsonl — full response trace (1,680 API calls)
src/
  evaluator.py      — model evaluation engine
  framework.py      — CyberEval framework core
  profiler.py       — deployment profiling
tests/
  test_manuscript_consistency.py
```

## Quick Start

```bash
# Install dependencies
uv sync

# Run the simulation (original framework)
python experiments/run_simulation.py

# Run the live MCQ evaluation (requires API keys)
python experiments/run_live_mcq.py
```

## Paper

**"Measuring the Ceiling: Evidence That Easy-to-Medium Cybersecurity MCQ Benchmarks Have Saturated for Current-Generation LLMs"**

- Justice Owusu Agyemang, Kwame Opuni-Boachie Obour Agyekum, Kwame Agyeman-Prempeh Agyekum, Francisca Adoma Acheampong, Jerry John Kponyo
- VIA Cybersecurity Lab & Quantum and Assistive Technologies Lab, KNUST, Ghana
- Targeted at IEEE Access
- 11 pages, 57 references, reproducible artifact

## License

MIT License
