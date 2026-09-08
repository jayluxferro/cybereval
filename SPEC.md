# SPEC — ARRAY-D-26-02880 Revision (Reviewers 1, 3, 6)

**Goal:** Address all 21 reviewer comments, strengthen the evidence base, and produce (a) a revised
manuscript, (b) a point-by-point response letter, and (c) a marked-up diff document (latexdiff PDF).

**Decision (user-confirmed):** expand the hard-question tail with ~40 new Tier 4/5 questions
(30 T4 + 10 T5) and re-run all 8 models live on them. Both API keys verified present:
DW creds at `/Users/jay/dev/pentest/audit/doubleword.ai/dw-mcp/creds.json`, OpenRouter key in env.

---

## Reviewer comment → change map

### Reviewer 1
| # | Comment | Change |
|---|---|---|
| R1-1 | Floor-test idea clearer in abstract/conclusion | Strengthen floor-test framing in abstract + Conclusion (already partly there; make explicit, narrow) |
| R1-2 | Only 9 T4 + 1 T5 questions; add more or scope claims | **Add 40 new T4/T5 questions + live run.** Bank: 210 → 250 items (37 T1, 116 T2, 47 T3, 39 T4, 11 T5). Update all distribution numbers everywhere |
| R1-3 | Parsing failures vs knowledge errors; relaxed parsing | New §5.3: error taxonomy (format vs knowledge) + relaxed-parser robustness re-score of all responses |
| R1-4 | Simulation vs live is between model generations; test simulation with current models | Reframe §5.2/§6.3 as *calibration gap*; add recalibration-on-live-data check (simulation re-fit to live scores → gap closes) |
| R1-5 | Typo "easyto medium" in abstract | Grep: not present in current main.tex (already fixed); verify in built PDF; note in response |
| R1-6 | How were difficulty levels assigned? rater agreement | Expand §3.2: rubric, who rated, procedure; add empirical item-level validation (§5.4 new): observed error rate by tier, point-biserial/discrimination, IRT difficulty (code exists: `compute_irt_difficulty`) |
| R1-7 | T5 based on 1 question; remove from trendline/annotate | Regenerate `figures/live_difficulty.pdf`: drop T5 marker from trend fit, annotate n=1 (or hide); after expansion T5 has n=11 → keep with annotation |
| R1-8 | §5.5: token/latency confounded by provider prompts/wrappers/reasoning settings | Add confound discussion sentence in §5.5 |

### Reviewer 3
| # | Comment | Change |
|---|---|---|
| R3-1 | Claims broader than evidence; heuristic internal difficulty; need validation + item analysis | Expansion (40 items) + §3.2 procedure detail + §5.4 empirical validation (item stats, tier–error correlation) + narrow claims throughout ("this question bank", not "MCQ benchmarks in general") |
| R3-2 | Wilson CI overlap ≠ indistinguishability; paired item-level analysis | Replace CI-overlap claims with **pairwise McNemar tests** on 210 (→250) paired item responses; new Table: pairwise p-values; rewrite §4.4 + §5.1 + Conclusion |
| R3-3 | 39.5 pp improvement not demonstrated; reframe as calibration gap | Rename §5.2 "Simulation calibration gap"; remove "capability improvement trajectory" contribution; recalibration check; rewrite abstract/conclusion claims |
| R3-4 | Reproducibility: exact model IDs, dates, system prompts, reasoning settings, retries, token accounting, routing, repeats | New reproducibility paragraph/table in §4: exact API model IDs (have them from `run_live_mcq.py`), no system prompt, temp 0, max_tokens 50, no retries (single pass), token = `usage.total_tokens`, dates from artifact (2026-05-28/29 window), note temp-0 ≠ full repeatability |
| R3-5 | Parser validation; report format-following separately; manual check; robust extraction | New analysis: relaxed parser (first standalone A–D; last letter; any letter), classify each error as format vs wrong-letter; manually list all parse-failure raw outputs; report corrected scores table; show main result robust |
| R3-6 | 90% floor threshold unsupported; no human baseline | Soften: "illustrative operational threshold", remove "clearly unsuitable for deployment" claims; add explicit statement that deployment validity needs human baseline + deployment study; narrow in abstract/conclusion |
| R3-7 | Refs [42][43][44] arXiv IDs are unrelated papers; update related work | Verified: [42]=jha2024secureval (arXiv:2407.12345 fake), [43]=chen2024cyberllm (2406.12345 fake), [44]=wang2024securityeval (2405.12345 fake). **Replace with real verified papers**; audit ALL 57 entries; add recent (2024–2025) cybersecurity/agentic eval refs |

### Reviewer 6
| # | Comment | Change |
|---|---|---|
| R6-1 | Difficulty validation needed | Same as R1-6/R3-1: §3.2 + §5.4 empirical validation |
| R6-2 | Unbalanced tier distribution | Same as R1-2: expansion |
| R6-3 | Paired item-level comparison | Same as R3-2: McNemar |
| R6-4 | 90% threshold weakly justified, deployment claims too strong | Same as R3-6: soften |
| R6-5 | 39.5 pp = simulation calibration gap | Same as R3-3: reframe |
| R6-6 | Parsing failures = incorrect vs measurement noise; is instruction-following part of benchmark? | State explicitly: format compliance is part of the benchmark protocol (single-letter contract); report both strict and relaxed scores; §5.3 taxonomy |

---

## Component breakdown & workstreams

### WS-1 Question bank expansion (critical path — main agent, user reviews)
- Author 40 new questions in the exact tuple format of `experiments/run_real_evaluation.py` `generate_question_bank()`:
  `( "question", ["A","B","C","D"], correct_idx, difficulty )`
- Distribution: 30 T4 (≈4–5 per dimension) + 10 T5 (1–2 per dimension), 7 dimensions: VK, TI, SC, IR, CG, FA, SA.
- Quality bar: T4 = multi-concept synthesis, applied scenarios, real protocol/tooling edge cases;
  T5 = expert-level, adversarial/exotic edge cases (the existing T4 items are too easy — new items must
  genuinely stress frontier models). Plausible distractors. No question text from certification exams.
- Deliverables:
  - `paper/artifacts/question_bank_new_t45.json` (new items only, schema: id/dimension/question/choices/correct/difficulty) — **for user review**
  - After approval: appended into `experiments/run_real_evaluation.py` (new section in `generate_question_bank`), and merged into `experiments/results/question_bank.json` (ids T4-x / continue numbering per dimension, e.g. `VK-030`…).

### WS-2 Live re-run on new questions (after WS-1 approval)
- Extend `experiments/run_live_mcq.py`: new script `experiments/run_live_mcq_t45.py` evaluating only the
  new 40 questions across the same 8 MODELS (same endpoints/payload: temp 0, max_tokens 50, no system prompt),
  but ALSO logging `timestamp_utc` per call (fixes R3-4 date reproducibility).
- Output: `experiments/results/live_mcq/t45_results.jsonl` (append mode safe).
- ~320 calls; expected < 30 min.

### WS-3 Offline re-analysis (agent — parallel with WS-1, re-run after WS-2)
Script: `experiments/analyze_revision.py` (new) producing `experiments/results/revision_analysis.json`:
1. **Relaxed parsing re-score** of `live_mcq/results.jsonl` (8 models × 210) and later `t45_results.jsonl`:
   - strict = existing pipeline result; relaxed = first standalone `\b[A-D]\b`; last-letter; any-letter.
   - Error taxonomy per incorrect item: FORMAT (no letter / unparseable) vs WRONG (letter ≠ ground truth).
   - Dump every FORMAT raw response to `experiments/results/parse_failures.jsonl` (manual check list for R3-5).
2. **Pairwise McNemar** (exact, with continuity correction) over paired item responses for all 28 model pairs
   on the full (expanded) bank; table for manuscript.
3. **Item-level stats**: per-item error rate across models; point-biserial correlation (item score vs total score)
   per item; IRT logit difficulty (reuse `compute_irt_difficulty` logic); tier × observed-error summary;
   Spearman correlation between assigned tier and observed error rate (difficulty-label validation for R1-6).
4. **Simulation recalibration check** (R1-4/R3-3): using `run_simulation.py` mechanics, refit simulation
   profile accuracy to current live scores (per dimension), show recalibrated simulation reproduces live
   ranking/levels → supports "calibration gap, not simulation error" framing.
5. Figures data: updated per-tier accuracy table incl. new items.

### WS-4 Reference audit (agent — parallel, web search required)
- Fix [42]–[44] (fabricated). Candidate verified replacements (agent MUST verify via search before use):
  - jha2024secureval → real secure-coding/val-eval paper (e.g., "CyberPal: A Benchmark..." 2025 — verify).
  - chen2024cyberllm → real survey, e.g. Jampen et al. "A Survey on Large Language Models for Cybersecurity" arXiv:2405.01160 (verify).
  - wang2024securityeval → real security-reasoning eval (verify candidate; e.g., CyberReasonBench or similar).
- Audit suspicious entries: liu2024benchmarking, park2024pentestbench (real PentestBench = Hu et al.? verify),
  roy2024llmpentest, guo2024can, ott2022fairness, ganguli2022predictability, fang2024llmagent, happe2023pwned,
  srivastava2023gsm8k (title=Beyond the Imitation Game; check key/title match), deng2023pentestgpt title/ID.
- Add 2–4 recent (2025) cybersecurity/agentic-evaluation refs to Related Work.
- Every added/replaced entry: real arXiv ID/DOI verified by search. Report per-entry verdicts.

### WS-5 Manuscript revision (main agent — after WS-2/3/4 outputs)
Edit `paper/main.tex`:
- Abstract: floor-test emphasis, calibration-gap language, 250-item bank, McNemar result, softened 90% claim.
- §1 contributions: remove "capability improvement trajectory" as contribution; replace with calibration-gap + paired-stat + expanded-bank contributions; fix enumeration.
- §2 Related Work: new refs; recalibrate "40–70%" contrast statements if needed.
- §3.2: detailed difficulty-assignment procedure + validation approach; 250-item distribution.
- §3.4: parser description + relaxed-parser robustness protocol; format compliance as part of protocol (R6-6).
- §4: exact model IDs table note, reproducibility paragraph (dates, prompts, retries, tokens, routing, single-pass, temp-0 caveat).
- §4.4: replace "no NHST" + CI-overlap reasoning with paired McNemar design.
- §5.1: McNemar results; drop "statistically indistinguishable via overlapping CIs" claims; keep Nemotron separation.
- §5.2: rename "Simulation calibration gap"; recalibration evidence; remove "+39.5 pp capability improvement" language → "calibration gap".
- §5.3: error taxonomy + relaxed scores + parse-failure examples.
- §5.4: updated tier table (39 T4, 11 T5), tier validation stats; figure w/o T5 trendline artifact (R1-7).
- §5.5: provider-confounding sentence (R1-8).
- §6: floor-test section softened (illustrative threshold; deployment claim narrowed); calibration-gap discussion.
- §7 Limitations: updated (single snapshot; label validation limits; no human baseline; temp-0 repeatability).
- §8 Conclusion: floor-test + calibration gap + expanded tail + McNemar summary.
- Grep all "210", "200 of 210", "10 items at tiers 4–5", "1 at tier 5", "37/116/47/9/1" numbers → update to 250-bank.
- Verify "easyto" absent (R1-5).

### WS-6 Figures (agent or main)
- `live_difficulty.pdf/.png`: regenerate with 5 tiers (T4 n=39, T5 n=11) and a linear fit **excluding T5**, annotated sample sizes (R1-7 satisfied with real data).
- `live_main_results.pdf/.png`: update with McNemar-informed caption or keep, add CI error bars note.
- Optional new figure: pairwise McNemar significance matrix heatmap.
- Figure code lives in a new `experiments/make_revision_figures.py`; source data from `revision_analysis.json`.

### WS-7 Documents (main agent)
- `reviews/response_to_reviewers.md`: point-by-point reply to all 21 comments, quoting new text, citing new tables/figures/refs.
- `reviews/CHANGES.md`: summary of every substantive change.
- `reviews/main_latexdiff.pdf`: `latexdiff` old (git HEAD) vs new main.tex, compiled.

### WS-8 Verification
- Two-pass pdflatex; grep log for Error|Warning|Overfull.
- `pytest tests/test_manuscript_consistency.py` (fix test if it hardcodes 210-bank numbers — it checks simulation numbers, likely unaffected, verify).
- All tables/figures numbers cross-checked against `revision_analysis.json`.
- bib: no unresolved citations (grep "Citation ... undefined"), 57+ entries.

---

## File map
- `experiments/run_real_evaluation.py` — question bank source (append 40 items)
- `experiments/results/question_bank.json` — exported bank artifact (merge new items)
- `experiments/run_live_mcq_t45.py` — NEW live-run script for new items (with timestamps)
- `experiments/results/live_mcq/t45_results.jsonl` — NEW live results
- `experiments/analyze_revision.py` — NEW re-analysis (parsing/McNemar/item stats/recalibration)
- `experiments/results/revision_analysis.json`, `parse_failures.jsonl` — NEW outputs
- `experiments/make_revision_figures.py` — NEW figure script
- `paper/main.tex`, `paper/references.bib` — revised manuscript
- `paper/figures/*.pdf|png` — regenerated
- `reviews/response_to_reviewers.md`, `reviews/CHANGES.md`, `reviews/main_latexdiff.pdf` — NEW deliverables

## Success metrics
- All 21 comments addressed with either new evidence or explicit narrowed claims (none ignored).
- New bank: 250 items, T4=39, T5=11, all 8 models scored on all items.
- Paired McNemar table present; no CI-overlap-as-significance claims remain.
- Zero unverified/fabricated references (placeholder arXiv IDs gone).
- Clean compile; consistency test passes; latexdiff PDF renders.

## Execution order
1. SPEC (this file) ✅
2. WS-1 draft questions → **user review gate**
3. WS-3, WS-4 agents run in parallel while user reviews
4. User approves → WS-2 live run
5. WS-3 re-run on expanded data → WS-6 figures → WS-5 manuscript → WS-8 verify → WS-7 documents
6. Commit on branch `array-revision` (local only; no push)

---

## ADDENDUM (2026-09-08): findings that changed the plan

### A. Degenerate answer key discovered (CRITICAL, fixed)
WS-3 analysis found **all 210 original items carry the correct answer at option A**
(verified: Counter = {0: 210}). An "always A" model scores 100%. Claude/Gemma
answered "A" for nearly every question in the original trace. Also found: token-total
mismatches for 2 models vs the paper table, and mixed parser conventions in the old
JSONL (28 Nemotron rows follow last-letter parsing).

**User-approved fix:** full clean re-run of all **250 questions with balanced answer
positions** (62/62/63/63 via deterministic seeded shuffle, `experiments/balance_bank.py`,
seed 13). New clean runner `experiments/run_live_mcq_v2.py` → `v2_results.jsonl`
with per-call `ts_utc` and `served_model`. This supersedes the separate T4/5-only run
(`t45_results.jsonl` kept only as provenance).

### B. Provider serving change: reasoning-mode models (handled)
Between the original evaluation and the revision, several models began to be
served in reasoning mode; under the original 50-token budget they consumed the
entire budget mid-reasoning and returned empty responses. Fixed by raising the
protocol budget uniformly to 2,048 tokens (documented in paper §4.2); the
affected intermediate run is retained as provenance (`v2_max50_provenance.jsonl`).

### C. References audit complete (WS-4)
57 → 61 entries, zero fabricated entries remain, every citation key preserved.
3 reviewer-flagged entries replaced with verified real papers; 8 other fabricated/
incorrect entries replaced/fixed; 4 new verified 2024–2026 refs added (uncited —
to be cited in Related Work): `shahriar2025agenticsecurity`, `challita2025redteamllm`,
`lukosiute2025risk`, `conde2026pentestwild`. See `reviews/reference_audit.md`.
**MS-edit required:** Related Work prose naming old authors/venues must be updated.

### D. Consistency test is stale
`tests/test_manuscript_consistency.py` fails against the current manuscript even
before our changes (it pins the pre-Array-conversion content). Rewrite it after the
manuscript revision to pin the new live numbers (250-item bank, balanced counts,
McNemar table presence, v2 token totals).

### E. New analyses after v2 lands
1. Re-run `analyze_revision.py` extended to the full 250-item v2 dataset
   (relaxed parsing, error taxonomy, McNemar 28 pairs, item stats, tier validation).
2. Run `experiments/simulation_recalibration.py` (R1-4/R3-3): refit simulation
   profile on current live data, show gap closes → calibration gap, not simulation error.
3. Regenerate all live figures from v2 data (`live_main_results`, `live_difficulty`
   incl. T5 with n=11, `live_token_efficiency`, `live_sim_vs_live` with recalibration).
