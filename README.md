# CyberEval

**Measuring the Ceiling: Evidence That Easy-to-Medium Cybersecurity MCQ Benchmarks Have Saturated**

CyberEval evaluates LLM cybersecurity competence across 7 dimensions using a 210-item MCQ question bank. It provides reproducible, live-API evidence that easy-to-medium cybersecurity MCQs have saturated for current-generation models.

## Live Evaluation Results (May 2026)

8 models evaluated across 210 questions:

| Model | Score | Provider |
|-------|-------|----------|
| Kimi-K2.6 | 100.0% | Moonshot AI |
| Claude-Sonnet-4.6 | 100.0% | Anthropic |
| Gemma-4-31B | 100.0% | Google |
| DeepSeek-V4-Pro | 99.5% | DeepSeek |
| Qwen-3.5-9B | 99.5% | Alibaba |
| DeepSeek-V4-Flash | 96.2% | DeepSeek |
| Qwen-3.6-35B | 91.0% | Alibaba |
| Nemotron-Super-120B | 85.7% | NVIDIA |

**Key finding:** 7/8 models score at or above 91.0%. 3 models achieve perfect scores. The easy-to-medium MCQ format no longer discriminates between competent models — it can only flag clearly unsuitable ones (floor test).

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
  main.tex          — IEEE Access paper (IEEEtran, 11 pages, 57 refs)
  main.pdf          — compiled paper
  figures/          — 3 live-data figures (main results, sim vs live, token efficiency)
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
