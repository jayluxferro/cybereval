# CyberEval Array Release Notes — ARRAY-D-26-02880, Round 2

Release date: 2026-10-01. This release is the reproducibility artifact for the round-2 revision of "Measuring the Ceiling: Evidence That Easy-to-Medium Cybersecurity MCQ Benchmarks Have Saturated for Current-Generation LLMs".

## Contents

- `data/question_bank.json` — the 250-item question bank: question text, four choices per item, ground-truth answer index, difficulty tier (1–5), and security dimension (VK, TI, SC, IR, CG, FA, SA). Correct-answer positions are balanced across A/B/C/D at 62/63/63/62 (fixed-letter ceiling: 25.2%).
- `data/bank_balance_provenance.json` — provenance of the balanced option ordering.
- `data/round2_validated/full_run.jsonl` — the validated re-measurement: 2,000 rows (8 models × 250 items), each with complete answer content (`raw_full`), complete reasoning content (`reasoning_full`), provider-reported `finish_reason`, `served_model`, token usage, and per-call UTC timestamp. Single continuous window, 2026-10-01 18:37–18:52 UTC.
- `data/round2_validated/docket.jsonl` — the adjudication docket: every response on which the four extractors disagree or a format flag is raised, with the adjudicated answer, verdict, and flags. (On this run the extractors agree on all 2,000 rows; the docket contains the 21 generation-budget-exhaustion rows.)
- `data/round2_validated/validated_answers.json` — the validated answer set used for every analysis in the paper, with the four extractor values (strict/first/last/any) per row for all 2,000 responses.
- `data/round2_validated/summary.txt` — the computed summary: per-model scores, Wilson CIs, McNemar results, per-tier error rates, Spearman correlation, hard-tail split.
- `data/round2_validated/simulation_recalibration.json` — the recalibration experiment on validated data.
- `data/original_protocol_run/v2_results.jsonl` — the 2026-09-08 protocol run trace (2,000 rows, 300-char stored prefixes), retained as provenance for the parser-artifact analysis of Section 5.3.
- `data/original_protocol_run/v2_max50_provenance.jsonl` — the superseded 50-token-budget run, retained as provenance for the protocol change documented in Section 4.2.
- `scripts/` — `run_full_recapture.py` (the validated run), `analyze_validated.py` (all analyses), `make_round2_figures.py` (all figures), `run_live_mcq_v2.py` and `analyze_revision_v2.py` (the earlier protocol-run pipeline).

## Protocol

- Prompt: "Cybersecurity MCQ. Choose the BEST answer. Reply with ONLY the letter (A, B, C, or D)." followed by the question, four lettered options, and "Your answer (single letter):". No system prompt.
- Sampling: temperature 0.0, max_tokens 2048, no other sampling parameters.
- Providers: DoubleWordAI (`https://api.doubleword.ai`) for seven models; OpenRouter (`https://openrouter.ai`) for Claude-Sonnet-4.6.
- Model identifiers: `deepseek-ai/DeepSeek-V4-Pro`, `deepseek-ai/DeepSeek-V4-Flash`, `moonshotai/Kimi-K2.6`, `Qwen/Qwen3.6-35B-A3B-FP8`, `Qwen/Qwen3.5-9B`, `google/gemma-4-31B-it`, `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` (DoubleWordAI); `anthropic/claude-sonnet-4-6` (OpenRouter).
- Every `served_model` identifier in the validated run matches the corresponding identifier in the 2026-09-08 run (zero provider-side drift).

## Adjudication rubric (pre-registered)

1. If the response contains a reasoning marker (`</think>`), the final answer is the last standalone A–D letter after the last marker; letters inside reasoning blocks are extraction noise.
2. Without a marker, a response consisting of a single letter is that letter.
3. Without a marker and with multiple letters, the last standalone letter is the answer.
4. An empty answer content with `finish_reason="length"` and non-empty reasoning content is a generation-budget exhaustion and is scored as a format error.

## Reproduction

1. `python3 scripts/run_full_recapture.py` (requires the provider keys used in the paper; idempotent; failed calls are retried up to four times with 2/4/8 s backoff and any remaining error rows are completed by re-running the script).
2. `python3 scripts/analyze_validated.py` — re-derives every score, CI, McNemar test, tier statistic, correlation, and hard-tail split in the paper, and writes the adjudication docket and the validated answer set (with per-row extractor values).
3. `python3 scripts/simulation_recalibration_validated.py` — reproduces the recalibration experiment (58.8% prior profile vs. 93.6% recalibrated vs. 98.0% live reference).
4. `python3 scripts/make_round2_figures.py` — regenerates all data figures.

All post-inference processing is deterministic. Raw model inference cannot be bit-reproduced (temperature 0.0 does not guarantee repeatability of hosted outputs), which is why the complete traces are released.
