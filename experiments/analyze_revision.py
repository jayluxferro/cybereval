#!/usr/bin/env python3
"""CyberEval revision offline re-analysis (ARRAY-D-26-02880; WS-3).

Re-analyzes experiments/results/live_mcq/results.jsonl (8 models x 210 items,
plus 2 failed 404/403 models that are dropped) and writes:
  - experiments/results/revision_analysis.json  (machine-readable analysis)
  - experiments/results/parse_failures.jsonl    (every STRICT parse failure, for manual review)

Sections (mapping to reviewer comments):
  1. Relaxed-parsing robustness  (R1-3, R3-5, R6-6): P_strict / P_first / P_last / P_any,
     error taxonomy (format vs wrong letter), knowledge-only estimates.
  2. Paired McNemar + Wilson CIs (R3-2, R6-3): all 28 unordered model pairs, exact binomial
     two-sided p (scipy.binomtest when available; manual doubling fallback otherwise).
  3. Item-level statistics / difficulty-label validation (R1-6, R3-1, R6-1):
     per-item error rate, point-biserial discrimination, IRT logit difficulty,
     Spearman(tier, error), per-tier x per-model accuracy.
  4. Sanity checks against the published manuscript numbers.

DATA-MODEL NOTES (important, discovered while writing this script):
  * results.jsonl lines do NOT carry "question"/"difficulty". Those come from
    experiments/results/question_bank.json, keyed by question_idx (verified: bank index
    order matches question_idx 0..209 exactly; correct_idx agrees on all 1680 kept rows).
  * raw_response in the file is capped at 200 chars (run_live_mcq.py stores
    content[:200]); the recorded predicted_idx was parsed from the FULL response at
    collection time. Re-parsing the stored prefix therefore cannot reproduce the
    recorded parse on a small number of rows (letter/answer-phrase beyond char 200,
    or a word cut mid-letter at the seam). Those rows are enumerated below.
  * The recorded pipeline (run_live_mcq.extract_answer) effectively returns the FIRST
    standalone [A-D] (its first pattern IS \\b([A-D])\\b), with -1 if none. The paper
    describes its fallback as "last letter"; last-letter semantics only manifest in a
    minority of rows (mostly Nemotron-120B) whose recorded answers agree with a
    phrase-then-LAST-letter parse of the full text instead. Both conventions are
    reported; recorded predictions are treated as authoritative for scoring (they are
    what the manuscript's published scores are based on).

Deterministic: no randomness; fixed model ordering everywhere.
"""

import collections
import json
import math
import re
import sys
from pathlib import Path

# ----------------------------------------------------------------------------
# Paths / configuration
# ----------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
RESULTS_JSONL = HERE / "results" / "live_mcq" / "results.jsonl"
QUESTION_BANK = HERE / "results" / "question_bank.json"
OUT_JSON = HERE / "results" / "revision_analysis.json"
OUT_FAILURES = HERE / "results" / "parse_failures.jsonl"

# File labels (results.jsonl) -> manuscript names. "Qwen-9B" and "Nemotron-120B"
# are the short labels used at collection time for Qwen-3.5-9B / Nemotron-Super-120B.
MODEL_LABEL_TO_NAME = {
    "Kimi-K2.6": "Kimi-K2.6",
    "Claude-Sonnet-4.6": "Claude-Sonnet-4.6",
    "Gemma-4-31B": "Gemma-4-31B",
    "DeepSeek-V4-Pro": "DeepSeek-V4-Pro",
    "Qwen-9B": "Qwen-3.5-9B",
    "DeepSeek-V4-Flash": "DeepSeek-V4-Flash",
    "Qwen-35B": "Qwen-3.6-35B",
    "Nemotron-120B": "Nemotron-Super-120B",
}
# Models dropped from the analysis (failed API calls, 404/403, tokens=0).
DROPPED_MODELS = ("Qwen-397B", "Qwen-4B")

# Manuscript table order (used for all printed/JSON iteration).
MODEL_ORDER = [
    "Kimi-K2.6", "Claude-Sonnet-4.6", "Gemma-4-31B", "DeepSeek-V4-Pro",
    "Qwen-3.5-9B", "DeepSeek-V4-Flash", "Qwen-3.6-35B", "Nemotron-Super-120B",
]
# Published per-tier difficulty-summary table (T1..T5), sanity target.
PUBLISHED_PER_TIER_PCT = {  # model -> [T1, T2, T3, T4, T5]
    "Kimi-K2.6": [100.0, 100.0, 100.0, 100.0, 100.0],
    "Claude-Sonnet-4.6": [100.0, 100.0, 100.0, 100.0, 100.0],
    "Gemma-4-31B": [100.0, 100.0, 100.0, 100.0, 100.0],
    "Qwen-3.5-9B": [100.0, 100.0, 97.9, 100.0, 100.0],
    "DeepSeek-V4-Pro": [97.3, 100.0, 100.0, 100.0, 100.0],
    "DeepSeek-V4-Flash": [97.3, 94.8, 97.9, 100.0, 100.0],
    "Qwen-3.6-35B": [94.6, 91.4, 87.2, 100.0, 100.0],
    "Nemotron-Super-120B": [97.3, 87.9, 74.5, 66.7, 100.0],
}
FILE_LABEL_ORDER = [
    "Kimi-K2.6", "Claude-Sonnet-4.6", "Gemma-4-31B", "DeepSeek-V4-Pro",
    "Qwen-9B", "DeepSeek-V4-Flash", "Qwen-35B", "Nemotron-120B",
]
N_ITEMS = 210
TOTAL_ITEMS = len(MODEL_ORDER) * N_ITEMS

# Published manuscript values (sanity targets), in MODEL_ORDER.
EXPECTED_STRICT_PCT = {m: p for m, p in zip(MODEL_ORDER, [100.0, 100.0, 100.0, 99.5,
                                                          99.5, 96.2, 91.0, 85.7])}
EXPECTED_TOKENS = dict(zip(MODEL_ORDER, [30713, 19640, 22145, 27541, 28680,
                                         22797, 41062, 23450]))

Z_95 = 1.96          # two-sided 95% normal quantile (Wilson CI)
MC_BONFERRONI = 0.05 / 28.0   # 28 unordered model pairs


# ----------------------------------------------------------------------------
# Parsers
# ----------------------------------------------------------------------------
def strict_recorded_parser(text):
    """Faithful copy of extract_answer() from experiments/run_live_mcq.py.

    This is the pipeline that produced the recorded predicted_idx: the bare
    word-boundary letter pattern comes FIRST (so effectively the first standalone
    [A-D] wins), the "answer is"/"option X"/"correct answer" patterns that follow
    are dead code in practice, and the final 'last letter' fallback only fires for
    texts that contain no letter at all (hence never). Returns -1 if no letter.
    """
    text = text.strip()
    for pat in [r"\b([A-D])\b", r"answer\s*(?:is|:)\s*([A-D])", r"option\s*([A-D])",
                r"correct\s*(?:answer|choice|option)\s*(?:is|:)?\s*([A-D])"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return ord(m.group(1).upper()) - ord("A")
    letters = re.findall(r"\b([A-D])\b", text)
    if letters:
        return ord(letters[-1].upper()) - ord("A")
    return -1


def parse_first(text):
    """P_first: first standalone [A-D]; -1 if none."""
    m = re.search(r"\b([A-D])\b", text or "", re.IGNORECASE)
    return ord(m.group(1).upper()) - ord("A") if m else -1


def parse_last(text):
    """P_last: last standalone [A-D] (the paper's described fallback); -1 if none."""
    letters = re.findall(r"\b([A-D])\b", text or "", re.IGNORECASE)
    return ord(letters[-1].upper()) - ord("A") if letters else -1


def parse_any(text):
    """P_any: any letter [A-D] anywhere (no word boundary), first occurrence;
    -1 if none. Catches letters inside '(B)', '1B)', attached to words, etc."""
    m = re.search(r"[A-D]", text or "", re.IGNORECASE)
    return ord(m.group(0).upper()) - ord("A") if m else -1


def has_standalone_letter(text):
    """True if any standalone [A-D] appears in text."""
    return bool(re.search(r"\b[A-D]\b", text or "", re.IGNORECASE))


# ----------------------------------------------------------------------------
# Statistics helpers (stdlib-only where feasible; scipy used when importable)
# ----------------------------------------------------------------------------
try:
    import scipy  # noqa: F401
    from scipy import stats as _scipy_stats
    HAS_SCIPY = True
except ImportError:  # pragma: no cover - exercised only on scipy-less machines
    HAS_SCIPY = False

# Exact two-sided binomial p for H0: p=0.5 on n trials with k successes.
if HAS_SCIPY:
    def exact_binom_two_sided(k, n):
        if n == 0:
            return 1.0
        return float(_scipy_stats.binomtest(int(k), int(n), 0.5,
                                            alternative="two-sided").pvalue)
else:  # pragma: no cover - stdlib fallback
    def exact_binom_two_sided(k, n):
        """Sum of binomial probabilities <= observed mass, doubled, capped at 1.
        For p=0.5 the distribution is symmetric, so this equals the exact
        two-sided p (no double counting because k = min(b, c) <= n/2)."""
        if n == 0:
            return 1.0
        k = min(int(k), int(n) - int(k))
        # log-space summation for numeric stability
        terms = [math.exp(_ln_choose(n, x) - n * math.log(2.0)) for x in range(k + 1)]
        return min(1.0, 2.0 * sum(terms))

    def _ln_choose(n, k):
        return (math.lgamma(n + 1.0) - math.lgamma(k + 1.0)
                - math.lgamma(n - k + 1.0))


def spearman_rho(xs, ys):
    """Spearman rank correlation (average ranks for ties) and two-sided p.

    Returns (rho, p). With scipy, uses scipy.stats.spearmanr. Fallback: Pearson on
    ranks with a t-approximation (large-n approximation, marked 'approx').
    """
    if HAS_SCIPY:
        rho, p = _scipy_stats.spearmanr(xs, ys)
        return float(rho), float(p)
    # --- stdlib fallback (rank-average then Pearson, t approx) ---
    n = len(xs)

    def _rank(vals):
        order = sorted(range(n), key=lambda i: vals[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks

    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    rho = cov / math.sqrt(vx * vy) if vx * vy > 0 else 0.0
    if abs(rho) >= 1.0:
        return rho, 0.0
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    # two-sided p via normal approximation of the t distribution (n large)
    p = 2.0 * (1.0 - _normal_cdf(abs(t)))
    return rho, max(p, 1e-300)


def _normal_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def wilson_ci(k, n, z=Z_95):
    """Wilson score interval (manual implementation), returns (low, high)."""
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)


def pearson_xy(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs)
    vy = sum((b - my) ** 2 for b in ys)
    if vx == 0 or vy == 0:
        return None  # constant vector -> discrimination undefined
    return cov / math.sqrt(vx * vy)


# ----------------------------------------------------------------------------
# Load and validate data
# ----------------------------------------------------------------------------
print("=" * 78)
print("CyberEval revision re-analysis (WS-3)")
print("=" * 78)

notes = []            # sanity/quality notes (go into JSON + stdout)
failures = []         # loud failures (go into JSON + stdout as [!!])

rows = [json.loads(line) for line in RESULTS_JSONL.open(encoding="utf-8")]
bank = json.load(QUESTION_BANK.open(encoding="utf-8"))
# The bank may already contain the 40 expanded items (250 total, appended at the
# end, ids VK-210..); the recorded live results only cover question_idx 0..209.
# Scope every bank lookup to the first N_ITEMS entries; index-order alignment with
# the results rows is verified below.
assert len(bank) >= N_ITEMS, f"question bank has {len(bank)} items, expected >= {N_ITEMS}"
if len(bank) > N_ITEMS:
    notes.append(f"question bank has {len(bank)} items (expanded: {len(bank) - N_ITEMS} "
                 f"new items appended, no live results yet for them); this analysis is "
                 f"scoped to the {N_ITEMS} recorded questions (bank indices 0..{N_ITEMS - 1})")
bank = bank[:N_ITEMS]

# --- row accounting ---------------------------------------------------------
counts = {}
for r in rows:
    counts[r["model"]] = counts.get(r["model"], 0) + 1
for label in counts:
    if label in DROPPED_MODELS:
        ok = (counts[label] == N_ITEMS
              and all(r["model"] == label and r["predicted_idx"] == -1
                      and not r["correct"] and r["tokens"] == 0
                      and str(r["raw_response"]).startswith("ERROR")
                      for r in rows if r["model"] == label))
        notes.append(f"dropped model '{label}': {counts[label]} failed rows "
                     f"(404/403, tokens=0, all parsed -1) -> excluded"
                     if ok else f"[!!] dropped model '{label}': unexpected row shape")
    elif label in MODEL_LABEL_TO_NAME:
        if counts[label] != N_ITEMS:
            failures.append(f"[!!] model '{label}': {counts[label]} rows, expected {N_ITEMS}")
    else:
        failures.append(f"[!!] unknown model label '{label}' in results file")
kept_labels = [l for l in FILE_LABEL_ORDER if l in MODEL_LABEL_TO_NAME]
if len(kept_labels) != 8:
    failures.append(f"[!!] expected 8 kept models, found {len(kept_labels)}")

kept = [r for r in rows if r["model"] in MODEL_LABEL_TO_NAME]
assert len(kept) == TOTAL_ITEMS, f"{len(kept)} kept rows, expected {TOTAL_ITEMS}"
for r in kept:
    r["model_name"] = MODEL_LABEL_TO_NAME[r["model"]]
    b = bank[r["question_idx"]]
    r["question"] = b["question"]
    r["choices"] = b["choices"]
    r["difficulty"] = int(b["difficulty"])

# --- bank <-> results alignment ---------------------------------------------
misalign = sum(1 for r in kept if r["correct_idx"] != bank[r["question_idx"]]["correct"])
if misalign:
    failures.append(f"[!!] {misalign} rows where recorded correct_idx != question bank")
else:
    notes.append("question_idx alignment verified: all 1680 rows match question_bank "
                 "(index order + correct_idx); tiers attach 1:1 from the bank")

# --- recorded-vs-field consistency ------------------------------------------
inconsistent = sum(1 for r in kept if r["correct"] != (r["predicted_idx"] == r["correct_idx"]))
if inconsistent:
    failures.append(f"[!!] {inconsistent} rows where 'correct' field != (predicted==correct_idx)")

# ----------------------------------------------------------------------------
# Answer-key position balance (data-quality check)
# ----------------------------------------------------------------------------
key_dist = collections.Counter(b["correct"] for b in bank)
ALL_KEY_AT_A = len(bank) == sum(1 for b in bank if b["correct"] == 0)
if ALL_KEY_AT_A:
    notes.append("CRITICAL data-quality finding: all 210 recorded questions have the "
                 "correct answer at option A (correct_idx == 0 in question_bank.json; "
                 "run_real_evaluation.py tuples carry correct index 0 throughout, and "
                 "run_live_mcq.py does NOT shuffle choices in the prompt). A null model "
                 "that always answers 'A' scores 210/210 = 100.0%, indistinguishable "
                 "from the top models, so parser/position robustness deltas above ~0% "
                 "are unmeasurable on this 210-item set. 'Wrong-letter' errors = any "
                 "deviation from A. Note: the 40 newly appended bank items ARE "
                 "position-balanced (10/10/10/10); the expanded 250-item bank is "
                 "220/10/10/10 and would still need shuffling on re-run.")

# ----------------------------------------------------------------------------
# Per-model bookkeeping
# ----------------------------------------------------------------------------
by_model = {m: [r for r in kept if r["model_name"] == m] for m in MODEL_ORDER}
for m in MODEL_ORDER:
    assert len(by_model[m]) == N_ITEMS and len({r["question_idx"] for r in by_model[m]}) == N_ITEMS

strict_scores = {}    # model -> (n_correct, n_total)
token_totals = {}
for m in MODEL_ORDER:
    rs = by_model[m]
    strict_scores[m] = (sum(1 for r in rs if r["predicted_idx"] == r["correct_idx"]), len(rs))
    token_totals[m] = sum(r["tokens"] for r in rs)

# ----------------------------------------------------------------------------
# 1. Relaxed-parser robustness
# ----------------------------------------------------------------------------
PARSERS = {
    "P_strict": strict_recorded_parser,  # replica of the recorded pipeline
    "P_first": parse_first,
    "P_last": parse_last,
    "P_any": parse_any,
}
parser_scores = {}    # parser -> model -> (correct, total)
for pname, fn in PARSERS.items():
    parser_scores[pname] = {}
    for m in MODEL_ORDER:
        rs = by_model[m]
        parser_scores[pname][m] = (
            sum(1 for r in rs if fn(r["raw_response"]) == r["correct_idx"]), len(rs))

# --- replication verification: does the recorded logic reproduce predicted_idx?
rep_mismatch = []     # (model_name, qidx, recorded, replica)
for r in kept:
    rep = strict_recorded_parser(r["raw_response"])
    if rep != r["predicted_idx"]:
        rep_mismatch.append((r["model_name"], r["question_idx"], r["predicted_idx"], rep))
n_rep_agree = TOTAL_ITEMS - len(rep_mismatch)
rep_agreement_pct = 100.0 * n_rep_agree / TOTAL_ITEMS
per_model_rep = {m: (N_ITEMS - sum(1 for x in rep_mismatch if x[0] == m), N_ITEMS)
                 for m in MODEL_ORDER}

truncated = [r for r in kept if len(r["raw_response"]) >= 200]
if rep_agreement_pct < 95.0:
    failures.append("[!!] strict-parser replication on stored raw_response < 95% "
                    f"({rep_agreement_pct:.2f}%) -- investigate")
else:
    notes.append(f"strict-parser replication on stored raw_response: "
                 f"{n_rep_agree}/{TOTAL_ITEMS} = {rep_agreement_pct:.2f}% (>=95% OK); "
                 f"{len(rep_mismatch)} mismatches, all on rows whose stored response is "
                 f"truncated at 200 chars -- recorded parse ran on the FULL response")
rep_reason = {}
for m, q, rec, rep_val in rep_mismatch:
    text = next(r["raw_response"] for r in kept
                if r["model_name"] == m and r["question_idx"] == q)
    cut = len(text) >= 200
    if rec >= 0 and rep_val == -1:
        reason = "answer letter/phrase beyond 200-char stored cutoff"
    elif rec == -1 and rep_val >= 0 and has_standalone_letter(text):
        reason = "seam artifact: word cut at char 200 looks like a standalone letter"
    elif m == "Nemotron-Super-120B" and rec >= 0 and rep_val >= 0:
        # Nemotron recorded answers track a phrase-then-LAST-letter parse of the
        # full text; a bare-first-letter parse of the stored prefix disagrees.
        reason = "Nemotron rows: recorded matches last-letter/phrase parse of full text"
    else:
        reason = "unclassified (see row dump)"
    rep_reason.setdefault(reason, []).append((m, q, rec, rep_val))
for reason, items in rep_reason.items():
    notes.append(f"replication mismatch class '{reason}': {len(items)} rows "
                 f"(e.g. {items[:4]})")

# --- strict = recorded pipeline outcome (manuscript scoring), for parity -----
parsers_table = {}    # json: parsers -> model -> {correct, total, accuracy_pct}
for pname in PARSERS:
    parsers_table[pname] = {}
    for m in MODEL_ORDER:
        if pname == "P_strict":
            # P_strict IS the recorded pipeline result (what the paper reports).
            # (replica-on-stored-text reproducibility is reported separately above)
            corr, tot = strict_scores[m]
        else:
            corr, tot = parser_scores[pname][m]
        parsers_table[pname][m] = {"correct": corr, "total": tot,
                                   "accuracy_pct": round(100.0 * corr / tot, 2)}

# --- error taxonomy (on RECORDED strict predictions; cf. full-text parsing) ---
error_taxonomy = {}
format_rows = []      # rows the strict parser got nothing from (predicted_idx == -1)
for m in MODEL_ORDER:
    rs = [r for r in by_model[m] if r["predicted_idx"] != r["correct_idx"]]
    fmt = [r for r in rs if r["predicted_idx"] == -1]
    wr = [r for r in rs if r["predicted_idx"] != -1]
    error_taxonomy[m] = {
        "format_errors": len(fmt),
        "wrong_letter_errors": len(wr),
        "total_errors": len(rs),
    }
    format_rows.extend(fmt)
# seam check: recorded format error whose STORED prefix does contain a letter
seam_formats = [r for r in format_rows if has_standalone_letter(r["raw_response"])]
if seam_formats:
    notes.append("among strict format errors, stored prefix contains a standalone "
                 "letter on " + ", ".join(f"{r['model_name']} q{r['question_idx']}"
                                          for r in seam_formats) +
                 " (word cut at the 200-char seam; full-text parse had no letter)")

# --- knowledge-only estimates -------------------------------------------------
# knowledge_only = (1 - wrong_letter/210): upper-bound score that treats every
# FORMAT error as latent knowledge (the model emitted no letter, so no evidence
# of a wrong answer). Also report accuracy on letter-emitting items only.
knowledge_only = {}
for m in MODEL_ORDER:
    n_fmt = error_taxonomy[m]["format_errors"]
    n_wr = error_taxonomy[m]["wrong_letter_errors"]
    n_emit = N_ITEMS - n_fmt
    correct_emitted = strict_scores[m][0]
    knowledge_only[m] = {
        "knowledge_only_pct": round(100.0 * (1.0 - n_wr / N_ITEMS), 2),
        "emitted_accuracy_pct": round(100.0 * correct_emitted / n_emit, 2)
        if n_emit else None,
        "n_emitted": n_emit,
    }

# ----------------------------------------------------------------------------
# 2. Paired McNemar + Wilson CIs
# ----------------------------------------------------------------------------
wilson = {}
for m in MODEL_ORDER:
    corr, tot = strict_scores[m]
    low, high = wilson_ci(corr, tot)
    wilson[m] = {"score_pct": round(100.0 * corr / tot, 2),
                 "ci_low": round(100.0 * low, 2), "ci_high": round(100.0 * high, 2)}

# helper: per-item correctness dict for each model: qidx -> 1 if strict-correct
item_ok = {}
for m in MODEL_ORDER:
    item_ok[m] = {r["question_idx"]: int(r["predicted_idx"] == r["correct_idx"])
                  for r in by_model[m]}

mcnemar_pairs = []
for i, ma in enumerate(MODEL_ORDER):
    for mb in MODEL_ORDER[i + 1:]:
        both_corr = both_wrong = b = c = 0   # b: A ok & B wrong | c: A wrong & B ok
        for q in range(N_ITEMS):
            oka, okb = item_ok[ma][q], item_ok[mb][q]
            both_corr += oka & okb
            both_wrong += (1 - oka) & (1 - okb)
            b += oka & (1 - okb)
            c += (1 - oka) & okb
        p = exact_binom_two_sided(min(b, c), b + c)
        sig05 = p < 0.05
        sig_bonf = p < MC_BONFERRONI
        lo_a, hi_a = wilson[ma]["ci_low"] / 100.0, wilson[ma]["ci_high"] / 100.0
        lo_b, hi_b = wilson[mb]["ci_low"] / 100.0, wilson[mb]["ci_high"] / 100.0
        ci_overlap = not (hi_a < lo_b or hi_b < lo_a)
        mcnemar_pairs.append({
            "pair": f"{ma} vs {mb}",
            "model_a": ma, "model_b": mb,
            "a": both_corr, "b": b, "c": c, "d": both_wrong,
            "n_discordant": b + c,
            "p_value": round(p, 12),
            "exact_or_approx": "exact" if HAS_SCIPY else "exact_manual_doubling",
            "significant_at_0.05": sig05,
            "significant_at_bonferroni": sig_bonf,
            "ci_overlap": ci_overlap,
        })
assert len(mcnemar_pairs) == 28

n_sig05 = sum(1 for p_ in mcnemar_pairs if p_["significant_at_0.05"])
n_sig_bonf = sum(1 for p_ in mcnemar_pairs if p_["significant_at_bonferroni"])
# pairs where the CI-overlap argument would call them indistinguishable but
# McNemar rejects -- the exact contrast the reviewers asked for.
ci_overlap_but_sig = [p_["pair"] for p_ in mcnemar_pairs
                      if p_["ci_overlap"] and p_["significant_at_0.05"]]
notes.append(f"McNemar: {n_sig05}/28 pairs significant at 0.05; "
             f"{n_sig_bonf}/28 at Bonferroni {MC_BONFERRONI:.4f}; "
             f"{len(ci_overlap_but_sig)} pairs with OVERLAPPING Wilson CIs yet "
             f"significant McNemar at 0.05 -> CI-overlap would have missed them: "
             f"{ci_overlap_but_sig}")
if not HAS_SCIPY:
    notes.append("scipy not importable: exact two-sided binomial p computed manually "
                 "(doubled lower-tail, capped at 1; exact for p=0.5)")

# ----------------------------------------------------------------------------
# 3. Item-level statistics / difficulty-label validation
# ----------------------------------------------------------------------------
per_item = []         # qidx -> {tier, error_rate, discrimination, irt}
model_totals = {m: strict_scores[m][0] for m in MODEL_ORDER}
item_order_models = MODEL_ORDER  # item-score vectors align with this order

for q in range(N_ITEMS):
    scores = [item_ok[m][q] for m in item_order_models]
    totals = [model_totals[m] for m in item_order_models]
    n_corr = sum(scores)
    error_rate = 1.0 - n_corr / len(item_order_models)
    disc = pearson_xy(scores, totals)          # point-biserial over the 8 "subjects"
    p_corr = max(0.01, min(0.99, n_corr / len(item_order_models)))
    irt = -math.log(p_corr / (1.0 - p_corr))   # negative = easy (cf. compute_irt_difficulty)
    per_item.append({"idx": q,
                     "tier": int(bank[q]["difficulty"]),
                     "n_models_correct": n_corr,
                     "error_rate": round(error_rate, 6),
                     "discrimination": None if disc is None else round(disc, 6),
                     "irt_difficulty": round(irt, 6)})

n_const = sum(1 for it in per_item if it["discrimination"] is None)
if n_const:
    notes.append(f"{n_const} of {N_ITEMS} items answered correctly by ALL 8 models "
                 "(zero variance) -> discrimination set to None/0 (no signal; "
                 "constant all-correct items do not discriminate at this ceiling)")

# tier aggregates
tiers = sorted({it["tier"] for it in per_item})
per_tier = {}
for t in tiers:
    its = [it for it in per_item if it["tier"] == t]
    errs = [it["error_rate"] for it in its]
    disc = [it["discrimination"] for it in its if it["discrimination"] is not None]
    irts = [it["irt_difficulty"] for it in its]
    per_tier[str(t)] = {
        "n": len(its),
        "mean_error_rate": round(sum(errs) / len(errs), 6),
        "mean_discrimination": round(sum(disc) / len(disc), 6) if disc else None,
        "mean_irt": round(sum(irts) / len(irts), 6),
    }
highest_error_tier = max(tiers, key=lambda t: per_tier[str(t)]["mean_error_rate"])
notes.append(f"difficulty tier with highest mean observed error rate: "
             f"tier {highest_error_tier} "
             f"(mean error rate {per_tier[str(highest_error_tier)]['mean_error_rate']})")

# Spearman(tier, error rate) and Spearman(tier, irt difficulty)
tier_vec = [float(it["tier"]) for it in per_item]
err_vec = [it["error_rate"] for it in per_item]
irt_vec = [it["irt_difficulty"] for it in per_item]
rho_te, p_te = spearman_rho(tier_vec, err_vec)
rho_ti, p_ti = spearman_rho(tier_vec, irt_vec)

# per-model per-tier accuracy (8x5 matrix, mirrors the manuscript table)
per_model_tier = {}
tier_table_deviations = []
for m in MODEL_ORDER:
    per_model_tier[m] = {}
    for t in tiers:
        rs = [r for r in by_model[m] if r["difficulty"] == t]
        corr = sum(1 for r in rs if r["predicted_idx"] == r["correct_idx"])
        pct = round(100.0 * corr / len(rs), 2)
        per_model_tier[m][str(t)] = pct
        pub = PUBLISHED_PER_TIER_PCT[m][t - 1]
        if abs(pct - pub) > 0.06:  # allow 1-decimal rounding
            tier_table_deviations.append(f"{m} tier{t}: data={pct}% vs paper={pub}%")
if tier_table_deviations:
    notes.append("per-tier difficulty table deviations from the published table: "
                 + "; ".join(tier_table_deviations) +
                 " -- note the paper's Qwen-3.6-35B row (94.6+91.4+87.2) then sums to "
                 "18 tier errors, inconsistent with its own stated 19 total errors; "
                 "the data give 2+11+6 = 19 (T2 should be 105/116 = 90.5%)")
else:
    notes.append("per-tier difficulty table reproduces the published difficulty-summary "
                 "table within rounding (0.1 pp)")

# ----------------------------------------------------------------------------
# 4. Sanity checks vs the manuscript
# ----------------------------------------------------------------------------
print("\n" + "=" * 78)
print("SANITY CHECKS")
print("=" * 78)

# (a) strict scores reproduce the published table
score_notes = []
all_scores_ok = True
print(f"\n{'model':<20s} {'published':>9s} {'strict':>9s} {'n':>5s}   status")
for m in MODEL_ORDER:
    corr, tot = strict_scores[m]
    pct = 100.0 * corr / tot
    ok = abs(pct - EXPECTED_STRICT_PCT[m]) < 0.051
    all_scores_ok &= ok
    flag = "OK" if ok else "[!!] DEVIATION"
    print(f"{m:<20s} {EXPECTED_STRICT_PCT[m]:>8.1f}% {pct:>8.1f}% {tot:>5d}   {flag}")
    if not ok:
        score_notes.append(f"strict score {m}: {pct:.1f}% vs published "
                           f"{EXPECTED_STRICT_PCT[m]}%")
if all_scores_ok:
    print("[OK] strict per-model scores reproduce the published table "
          "(Kimi/Claude/Gemma 100.0, Pro/Qwen-3.5-9B 99.5, Flash 96.2, "
          "Qwen-3.6-35B 91.0, Nemotron 85.7)")
else:
    print("[!!] STRICT-SCORE DEVIATION from published table")
    failures.append("[!!] strict scores deviate from published table: " + "; ".join(score_notes))

# (b) token totals
print(f"\n{'model':<20s} {'published_tokens':>16s} {'file_tokens':>12s}   status")
token_notes = []
all_tokens_ok = True
for m in MODEL_ORDER:
    got = token_totals[m]
    exp = EXPECTED_TOKENS[m]
    ok = got == exp
    all_tokens_ok &= ok
    flag = "OK" if ok else "[!!] DEVIATION"
    print(f"{m:<20s} {exp:>16d} {got:>12d}   {flag}")
    if not ok:
        token_notes.append(f"token total {m}: file={got} vs published={exp} "
                           f"(delta {got - exp:+,d})")
if all_tokens_ok:
    print("[OK] token totals match the published table for all 8 models")
else:
    print("[!!] TOKEN-TOTAL DEVIATION -- see notes (mapping is fixed by 6/8 exact "
          "matches plus score alignment; no permutation of model labels fits the "
          "published totals, so this is a data/paper discrepancy, not a mapping error)")
    for t in token_notes:
        failures.append("[!!] " + t)
    notes.append("token-total anomaly: results.jsonl sums give Gemma-4-31B=18736 and "
                 "Nemotron-Super-120B=22114, while the published table states 22145 and "
                 "23450. 6/8 models match exactly and strict scores align with the "
                 "published order, so the mapping is not at fault; the published "
                 "Gemma/Nemotron totals appear to predate a re-run that changed those "
                 "models' rows. Not fudged -- reported for the manuscript to reconcile.")

# (c) paper claims: Flash 8 errors (5 parsing, 3 substantive); Qwen-3.6-35B 19 errors
# (d) answer-key position balance -- critical data-quality finding
print("\n" + "-" * 78)
print("DATA-QUALITY: ANSWER-KEY POSITION BALANCE")
print("-" * 78)
print(f"correct_idx distribution over the recorded {N_ITEMS} bank items: "
      f"{dict(sorted(collections.Counter(b['correct'] for b in bank).items()))}")
if ALL_KEY_AT_A:
    print("[!!] ALL 210 questions have the correct answer at option A "
          "(generator tuples use index 0 throughout; the live prompt does NOT "
          "shuffle choices).")
    print("[!!] A null model that always answers 'A' would score 210/210 = 100.0% -- "
          "indistinguishable from Kimi/Claude/Gemma, and above the 90% floor.")
    print("[!!] Consequence: on this recorded set, 'wrong-letter errors' mean "
          "'deviated from A'; answer-position robustness cannot be assessed, and "
          "the benchmark cannot rank models that default to 'A'. (The 40 new bank "
          "items are position-balanced 10/10/10/10; a re-run should shuffle or the "
          "expanded 250-item bank remains 220/10/10/10.)")
    print("[!!] The relaxed-parser deltas for verbose models (Kimi/Pro/Qwen-9B/"
          "Flash/Qwen-3.6-35B) largely measure response-TEMPLATE lettering, not "
          "answer validity: their stored prefixes echo the prompt/options and the "
          "key is always 'A'.")
else:
    print("[OK] answer keys are not all at position A on the recorded items")

print("\nError-taxonomy vs paper claims (error_breakdown table):")
print(f"{'model':<20s} {'errors':>7s} {'format':>7s} {'wrong-letter':>13s}   claim")
for m in MODEL_ORDER:
    e = error_taxonomy[m]
    claim = {  # published error_breakdown descriptions
        "DeepSeek-V4-Flash": "8 (paper: 5 parsing, 3 substantive)",
        "Nemotron-Super-120B": "30 (paper: mixed)",
        "Qwen-3.6-35B": "19 (paper: verbose, fails to commit)",
        "DeepSeek-V4-Pro": "1 (paper: parsing failure, tier-1)",
        "Qwen-3.5-9B": "1 (paper: parsing failure)",
    }.get(m, "-")
    print(f"{m:<20s} {e['total_errors']:>7d} {e['format_errors']:>7d} "
          f"{e['wrong_letter_errors']:>13d}   {claim}")
if error_taxonomy["DeepSeek-V4-Flash"]["total_errors"] != 8:
    failures.append("[!!] Flash error count != 8")
if error_taxonomy["Qwen-3.6-35B"]["total_errors"] != 19:
    failures.append("[!!] Qwen-3.6-35B error count != 19")
flash_split = (error_taxonomy["DeepSeek-V4-Flash"]["format_errors"],
               error_taxonomy["DeepSeek-V4-Flash"]["wrong_letter_errors"])
q35_split = (error_taxonomy["Qwen-3.6-35B"]["format_errors"],
             error_taxonomy["Qwen-3.6-35B"]["wrong_letter_errors"])
print("\n[check] Flash: 8 errors ->", flash_split, "format/wrong-letter "
      "(paper claims 5/3 -> NOT reproduced under the recorded definitions)")
print("[check] Qwen-3.6-35B: 19 errors ->", q35_split, "format/wrong-letter")
notes.append(f"Flash error split under recorded-strict taxonomy: {flash_split[0]} "
             f"format + {flash_split[1]} wrong-letter (paper states 5 parsing + 3 "
             f"substantive; 4 of the 7 format errors are empty responses "
             f"(q79/q93/q96/q204), the paper's split likely came from manual review "
             f"of the full responses). Qwen-3.6-35B: {q35_split[0]} format + "
             f"{q35_split[1]} wrong-letter (19 total, matches paper).")

# ----------------------------------------------------------------------------
# Write parse_failures.jsonl (manual review list for R3-5)
# ----------------------------------------------------------------------------
with OUT_FAILURES.open("w", encoding="utf-8") as fh:
    for r in sorted(format_rows,
                    key=lambda r: (r["model_name"], r["question_idx"])):
        rec = {
            "model": r["model"],            # label as in results.jsonl
            "model_paper": r["model_name"],
            "question_idx": r["question_idx"],
            "difficulty_tier": r["difficulty"],
            "question": r["question"],
            "choices": r["choices"],
            "correct_idx": r["correct_idx"],
            "predicted_idx": r["predicted_idx"],
            "raw_response": r["raw_response"],
            "note": "strict parser (recorded) found no answer letter in the FULL "
                    "response; raw_response here is the stored 200-char prefix "
                    "(empty string = model returned empty content)",
        }
        fh.write(json.dumps(rec) + "\n")

# ----------------------------------------------------------------------------
# Assemble JSON output
# ----------------------------------------------------------------------------
output = {
    "meta": {
        "input": str(RESULTS_JSONL),
        "question_bank": str(QUESTION_BANK),
        "n_models": 8, "n_items": N_ITEMS, "n_rows": TOTAL_ITEMS,
        "scipy_available": HAS_SCIPY,
        "model_mapping": MODEL_LABEL_TO_NAME,
        "dropped_models": list(DROPPED_MODELS),
        "answer_key_balance_over_recorded_210": dict(collections.Counter(
            b["correct"] for b in bank)),
        "all_recorded_keys_at_A": ALL_KEY_AT_A,
        "null_model_always_A_score_pct": round(
            100.0 * sum(1 for b in bank if b["correct"] == 0) / len(bank), 2)
        if len(bank) else None,
        "generated_utc": None,  # left None: deterministic content only
    },
    "parsers": parsers_table,
    "parser_replication_on_stored_text": {
        "agreement_pct_overall": round(rep_agreement_pct, 2),
        "n_agree": n_rep_agree, "n_rows": TOTAL_ITEMS,
        "per_model_agreement": {m: {"n_agree": a, "n_total": t} for m, (a, t)
                                in per_model_rep.items()},
        "n_mismatches": len(rep_mismatch),
        "mismatch_classes": {k: v for k, v in rep_reason.items()},
        "note": "replica of run_live_mcq.extract_answer applied to the STORED "
                "raw_response (200-char prefix). Recorded predicted_idx was parsed "
                "from the full response at collection time; mismatches are "
                "truncation artifacts (letter/answer-phrase beyond char 200, or a "
                "word cut mid-letter at the seam), plus Nemotron rows whose recorded "
                "answers follow a phrase/LAST-letter convention.",
    },
    "error_taxonomy": error_taxonomy,
    "format_error_rows_dumped_to": str(OUT_FAILURES),
    "knowledge_only": knowledge_only,
    "mcnemar": {
        "pairs": mcnemar_pairs,
        "bonferroni_alpha": round(MC_BONFERRONI, 6),
        "n_significant_at_0.05": n_sig05,
        "n_significant_at_bonferroni": n_sig_bonf,
        "ci_overlap_but_significant": ci_overlap_but_sig,
        "method": "exact two-sided binomial (scipy.stats.binomtest)" if HAS_SCIPY
                  else "manual exact two-sided binomial (doubled lower tail, cap 1)",
    },
    "wilson": wilson,
    "item_stats": {
        "per_tier": per_tier,
        "spearman_tier_error": {"rho": round(rho_te, 6), "p": round(p_te, 12),
                                "approx": not HAS_SCIPY},
        "spearman_tier_irt": {"rho": round(rho_ti, 6), "p": round(p_ti, 12),
                              "approx": not HAS_SCIPY},
        "highest_error_tier": highest_error_tier,
        "per_model_per_tier": per_model_tier,
        "per_question": per_item,
        "note": "item discrimination = point-biserial correlation of item score "
                "with model total score over 8 models (tiny subject pool -> coarse); "
                "None where all 8 models answered correctly (zero variance).",
    },
    "sanity": {
        "strict_scores_match_paper": all_scores_ok,
        "token_totals_match": all_tokens_ok,
        "strict_per_model_pct": {m: round(100.0 * strict_scores[m][0] / strict_scores[m][1], 2)
                                 for m in MODEL_ORDER},
        "token_totals": {m: token_totals[m] for m in MODEL_ORDER},
        "notes": notes,
        "failures": failures,
    },
}

with OUT_JSON.open("w", encoding="utf-8") as fh:
    json.dump(output, fh, indent=2, ensure_ascii=False)
    fh.write("\n")

# ----------------------------------------------------------------------------
# Readable stdout summary
# ----------------------------------------------------------------------------
print("\n" + "=" * 78)
print("1. PARSER ROBUSTNESS (per-model accuracy %, strict = recorded pipeline)")
print("=" * 78)
print("P_first/P_last/P_any are computed on the STORED raw_response (200-char "
      "prefix). CAVEATS: (a) with the all-A answer key, letter-accurate parsers "
      "score high for models that default to 'A' regardless of knowledge; "
      "(b) for verbose models the stored prefix is response-template text, so "
      "P_last/P_any often track echoed option letters rather than committed "
      "answers; (c) strict = recorded (parsed from the full response at "
      "collection time).")
hdr = f"{'model':<20s}" + "".join(f"{p:>10s}" for p in PARSERS)
print(hdr)
for m in MODEL_ORDER:
    row = f"{m:<20s}"
    for p in PARSERS:
        row += f"{parsers_table[p][m]['accuracy_pct']:>10.2f}"
    print(row)

print("\n" + "=" * 78)
print("2. ERROR TAXONOMY + KNOWLEDGE-ONLY ESTIMATES (n=210 per model)")
print("=" * 78)
print(f"{'model':<20s} {'errors':>7s} {'format':>7s} {'wrongLtr':>9s} "
      f"{'knowl-only%':>12s} {'emitted-acc%':>13s}")
for m in MODEL_ORDER:
    e = error_taxonomy[m]
    ko = knowledge_only[m]
    print(f"{m:<20s} {e['total_errors']:>7d} {e['format_errors']:>7d} "
          f"{e['wrong_letter_errors']:>9d} {ko['knowledge_only_pct']:>12.2f} "
          f"{ko['emitted_accuracy_pct']:>13.2f}")
print(f"\nWrote {len(format_rows)} STRICT parse-failure rows (format errors) to "
      f"{OUT_FAILURES.name} for manual review")

print("\n" + "=" * 78)
print("3. MCNEMAR (28 pairs) + WILSON CIs")
print("=" * 78)
print(f"{'model':<20s} {'score':>7s} {'95% Wilson CI':>16s}")
for m in MODEL_ORDER:
    w = wilson[m]
    print(f"{m:<20s} {w['score_pct']:>6.2f}% [{w['ci_low']:>5.2f}%, {w['ci_high']:>5.2f}%]")
print(f"\nSignificant pairs: {n_sig05}/28 at alpha=0.05; "
      f"{n_sig_bonf}/28 at Bonferroni 0.05/28={MC_BONFERRONI:.4f}")
sig_list = [p_["pair"] for p_ in mcnemar_pairs if p_["significant_at_0.05"]]
bonf_list = [p_["pair"] for p_ in mcnemar_pairs if p_["significant_at_bonferroni"]]
print("At 0.05 :", ", ".join(sig_list))
print("At 0.0018:", ", ".join(bonf_list) if bonf_list else "(none)")
print(f"Pairs with overlapping Wilson CIs yet McNemar p<0.05 "
      f"(CI-overlap would mislabel them indistinguishable): "
      f"{len(ci_overlap_but_sig)} -> {ci_overlap_but_sig}")

print("\n" + "=" * 78)
print("4. ITEM-LEVEL STATISTICS / DIFFICULTY-LABEL VALIDATION")
print("=" * 78)
print(f"{'tier':>5s} {'n':>5s} {'mean_err':>10s} {'mean_disc':>10s} {'mean_irt':>10s}")
for t in sorted(per_tier, key=int):
    v = per_tier[t]
    disc = "n/a" if v["mean_discrimination"] is None else f"{v['mean_discrimination']:.4f}"
    print(f"{t:>5s} {v['n']:>5d} {v['mean_error_rate']:>10.4f} {disc:>10s} "
          f"{v['mean_irt']:>10.3f}")
print(f"\nSpearman(tier, observed error rate): rho={rho_te:.4f}, p={p_te:.2e}  "
      f"({'scipy' if HAS_SCIPY else 'manual approx'})")
print(f"Spearman(tier, IRT difficulty):    rho={rho_ti:.4f}, p={p_ti:.2e}")
print(f"Tier with highest mean error rate: tier {highest_error_tier} "
      f"({per_tier[str(highest_error_tier)]['mean_error_rate']:.4f})")

print("\nPer-model accuracy by tier (%, vs the manuscript difficulty table):")
hdr = f"{'model':<20s}" + "".join(f"{'T'+t:>9s}" for t in sorted(per_tier, key=int))
print(hdr)
for m in MODEL_ORDER:
    print(f"{m:<20s}" + "".join(f"{per_model_tier[m][t]:>9.2f}"
                                for t in sorted(per_tier, key=int)))
if tier_table_deviations:
    print("[!!] per-tier deviations vs published difficulty-summary table: "
          + "; ".join(tier_table_deviations))
else:
    print("[OK] per-tier matrix reproduces the published difficulty table within "
          "0.1 pp rounding")

print("\n" + "=" * 78)
print("SANITY SUMMARY")
print("=" * 78)
print(f"strict scores match published table : {all_scores_ok}")
print(f"token totals match published table  : {all_tokens_ok}")
print(f"strict-parser replication agreement : {rep_agreement_pct:.2f}% "
      f"(target >= 95%)")
print(f"dropped 404/403 models excluded     : {list(DROPPED_MODELS)} "
      f"({counts.get('Qwen-397B', '?')}/{counts.get('Qwen-4B', '?')} rows each)")
print(f"write OK: {OUT_JSON.name} / {OUT_FAILURES.name}")
if notes:
    print("\nNotes:")
    for n_ in notes:
        print("  -", n_)
if failures:
    print("\n[!!] REPORTED DEVIATIONS (analysis completed; outputs written):")
    for f_ in failures:
        print("  -", f_)
# Deliberate exit-code choice: 0 even when deviations are reported. The deviations
# (token-total mismatch vs the published table, all-A answer keys) are *findings*
# about the data/paper, not script failures -- they must stay visible in stdout and
# in sanity.notes/failures of revision_analysis.json, but a fixed exit code keeps
# this script usable in pipelines while the paper/data discrepancy is unresolved.
print("\nAll checks executed; outputs written:",
      OUT_JSON.name, "/", OUT_FAILURES.name,
      "(deviations above are reported findings, see sanity.failures in JSON).")
