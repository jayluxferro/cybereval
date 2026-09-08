#!/usr/bin/env python3
"""CyberEval v2 revision re-analysis (balanced 250-item bank, clean single-pass run).

Re-analyzes experiments/results/live_mcq/v2_results.jsonl (8 models x 250 items,
2,000 rows; correct-answer positions balanced 62/62/63/63) and writes:
  - experiments/results/revision_analysis_v2.json
  - experiments/results/parse_failures_v2.jsonl

Sections (same analysis family as analyze_revision.py, which analyzed the v1 run
whose answer key was degenerate -- all correct answers sat at option A):
  1. Main results: per-model score over 250 + Wilson 95% CI; per-dimension (7x8)
     matrix; per-tier (5x8) matrix.
  2. Original-vs-new split: per-model score on the original 210 items (indices
     0-209, tiers 1-4 + 1 T5) vs the 40 new hard items (indices 210-249:
     30 x T4 + 10 x T5), incl. per-tier detail for the new 40. This is the key
     discrimination-on-the-hard-tail table.
  3. Parsing robustness: P_first / P_last / P_any / recorded-strict per model;
     error taxonomy (FORMAT = recorded strict found no letter, WRONG_LETTER =
     letter extracted but wrong); every FORMAT row dumped to parse_failures_v2.jsonl.
  4. Exact McNemar over all 28 unordered model pairs on the 250 paired items
     (scipy.stats.binomtest when importable; manual exact doubling otherwise).
  5. Item-level statistics: per-item error rate, point-biserial discrimination
     (item score vs model total over 8 models), IRT logit difficulty
     d = -ln(p/(1-p)), p clipped to [0.01, 0.99]; per-tier means;
     Spearman(tier, error rate) rho + p.
  6. Sanity: 2000 rows, 250 per model, no ERROR rows, no missing ts_utc,
     no duplicate (model, question_idx) pairs; served_model per model printed
     (version provenance for the paper's reproducibility section) and the
     ts_utc window.

v2 rows are self-contained (question text, difficulty, dimension included) and
carry the canonical model names, so no bank join or label mapping is needed; the
bank is still cross-checked for alignment as a sanity step.

Deterministic: no randomness; fixed iteration order everywhere.
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
RESULTS_JSONL = HERE / "results" / "live_mcq" / "v2_results.jsonl"
QUESTION_BANK = HERE / "results" / "question_bank.json"
OUT_JSON = HERE / "results" / "revision_analysis_v2.json"
OUT_FAILURES = HERE / "results" / "parse_failures_v2.jsonl"

N_ITEMS = 250          # full balanced bank
N_ORIGINAL = 210       # original items (indices 0-209)
N_NEW = 40             # new hard items (indices 210-249: 30 T4 + 10 T5)
EXPECTED_TOTAL_ROWS = 8 * N_ITEMS

# Canonical manuscript order (v2 rows already use these names).
MODEL_ORDER = [
    "Kimi-K2.6", "Claude-Sonnet-4.6", "Gemma-4-31B", "DeepSeek-V4-Pro",
    "Qwen-3.5-9B", "DeepSeek-V4-Flash", "Qwen-3.6-35B", "Nemotron-Super-120B",
]
Z_95 = 1.96
MC_BONFERRONI = 0.05 / 28.0   # 28 unordered model pairs

try:
    import scipy  # noqa: F401
    from scipy import stats as _scipy_stats
    HAS_SCIPY = True
except ImportError:  # pragma: no cover
    HAS_SCIPY = False


# ----------------------------------------------------------------------------
# Parsers (identical definitions to analyze_revision.py / run_live_mcq_v2.py)
# ----------------------------------------------------------------------------
def strict_recorded_parser(text):
    """Faithful copy of extract_answer() from run_live_mcq_v2.py (== original run's
    logic: bare word-boundary letter pattern first => effectively the FIRST
    standalone [A-D]; -1 if none)."""
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
    m = re.search(r"\b([A-D])\b", text or "", re.IGNORECASE)
    return ord(m.group(1).upper()) - ord("A") if m else -1


def parse_last(text):
    letters = re.findall(r"\b([A-D])\b", text or "", re.IGNORECASE)
    return ord(letters[-1].upper()) - ord("A") if letters else -1


def parse_any(text):
    m = re.search(r"[A-D]", text or "", re.IGNORECASE)
    return ord(m.group(0).upper()) - ord("A") if m else -1


# ----------------------------------------------------------------------------
# Statistics helpers
# ----------------------------------------------------------------------------
if HAS_SCIPY:
    def exact_binom_two_sided(k, n):
        if n == 0:
            return 1.0
        return float(_scipy_stats.binomtest(int(k), int(n), 0.5,
                                            alternative="two-sided").pvalue)
else:  # pragma: no cover - stdlib fallback
    def exact_binom_two_sided(k, n):
        """Doubled lower-tail binomial sum, capped at 1; exact for p=0.5
        (symmetric: k = min(b, c) <= n/2 avoids double counting)."""
        if n == 0:
            return 1.0
        k = min(int(k), int(n) - int(k))

        def _ln_choose(n_, k_):
            return (math.lgamma(n_ + 1.0) - math.lgamma(k_ + 1.0)
                    - math.lgamma(n_ - k_ + 1.0))
        terms = [math.exp(_ln_choose(n, x) - n * math.log(2.0)) for x in range(k + 1)]
        return min(1.0, 2.0 * sum(terms))


def spearman_rho(xs, ys):
    if HAS_SCIPY:
        rho, p = _scipy_stats.spearmanr(xs, ys)
        return float(rho), float(p)
    # --- stdlib fallback: rank-average then Pearson, t approx ---
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
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0))))
    return rho, max(p, 1e-300)


def wilson_ci(k, n, z=Z_95):
    """Wilson score interval (manual), returns (low, high) as proportions."""
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
        return None
    return cov / math.sqrt(vx * vy)


# ----------------------------------------------------------------------------
# Load + sanity the data
# ----------------------------------------------------------------------------
print("=" * 78)
print("CyberEval v2 re-analysis (balanced 250-item bank)")
print("=" * 78)

notes = []
failures = []

# Parse lines defensively: a crashed writer can leave a partial trailing line;
# a re-run of the idempotent runner leaves stale "ERROR:" rows behind while
# appending successful retries (old rows are never deleted). Stale ERROR rows
# are therefore dropped -- loudly -- and every accounting check runs on the
# clean set of successful rows.
raw_lines = [ln for ln in RESULTS_JSONL.open(encoding="utf-8") if ln.strip()]
rows, bad_lines = [], 0
for ln in raw_lines:
    try:
        rows.append(json.loads(ln))
    except json.JSONDecodeError:
        bad_lines += 1
stale = [r for r in rows
         if str(r.get("raw_response", "")).startswith("ERROR:")
         or (r.get("tokens", 0) == 0 and not r.get("served_model"))]
if stale:
    print(f"[note] dropping {len(stale)} stale ERROR rows from earlier "
          f"failed attempts (runner retried them; success rows carry the "
          f"final answers)")
    rows = [r for r in rows if r not in stale]
if bad_lines:
    print(f"[note] {bad_lines} partial/unparseable trailing line(s) dropped "
          f"(interrupted writer)")
bank = json.load(QUESTION_BANK.open(encoding="utf-8")) if QUESTION_BANK.exists() else None

# --- 6. sanity: row accounting ---------------------------------------------
failures.append(f"expected {EXPECTED_TOTAL_ROWS} successful rows, found {len(rows)}"
                if len(rows) != EXPECTED_TOTAL_ROWS else None)
counts = collections.Counter(r["model"] for r in rows)
for m in MODEL_ORDER:
    if counts[m] != N_ITEMS:
        failures.append(f"model {m}: {counts[m]} rows, expected {N_ITEMS}")
extra = set(counts) - set(MODEL_ORDER)
if extra:
    failures.append(f"unexpected model labels: {sorted(extra)}")

missing_ts = [r for r in rows if not r.get("ts_utc")]
if missing_ts:
    failures.append(f"{len(missing_ts)} rows missing ts_utc")
dupes = len(rows) - len({(r["model"], r["question_idx"]) for r in rows})
if dupes:
    failures.append(f"{dupes} duplicate (model, question_idx) rows")

# --- bank alignment cross-check ---------------------------------------------
# Analysis is anchored on the self-contained rows (each row carries the
# correct_idx / difficulty / dimension the model was graded against), so a
# bank mismatch is reported loudly as a finding, not treated as a hard failure
# (the bank file could in principle be re-balanced after the run completed).
if bank is not None and len(bank) >= N_ITEMS:
    mis = [r["question_idx"] for r in rows
           if r["question_idx"] < len(bank)
           and (r["correct_idx"] != bank[r["question_idx"]]["correct"]
                or r["difficulty"] != bank[r["question_idx"]]["difficulty"]
                or r["dimension"] != bank[r["question_idx"]].get("dimension")
                or r["question"] != bank[r["question_idx"]]["question"])]
    if mis:
        print(f"[!!] {len(mis)} v2 rows disagree with the current question_bank "
              f"on correct/difficulty/dimension/question (e.g. qidx {mis[:5]}) "
              f"-- bank may have been re-balanced AFTER the run; row-anchored "
              f"scores below are unaffected but paper-bank consistency needs review")
    else:
        notes.append("question_bank alignment OK: question text, correct_idx, "
                     "difficulty, dimension match bank rows on all 2000 v2 rows")

failures = [f for f in failures if f is not None]
if failures:
    print("[!!] SANITY FAILURES:")
    for f in failures:
        print("   ", f)
    sys.exit(1)

# --- served_model + ts window (reproducibility provenance) ------------------
served = {m: sorted({r["served_model"] for r in rows if r["model"] == m})
          for m in MODEL_ORDER}
ts_list = sorted(r["ts_utc"] for r in rows)
ts_min, ts_max = ts_list[0], ts_list[-1]
if any(len(v) != 1 for v in served.values()):
    print("[!!] multiple served_model values within one model label: "
          f"{ {m: v for m, v in served.items() if len(v) != 1} } -- label may "
          "have been routed across backends; interpretation caveat, analysis "
          "continues with all values reported")

by_model = {m: [r for r in rows if r["model"] == m] for m in MODEL_ORDER}
for m in MODEL_ORDER:
    by_model[m].sort(key=lambda r: r["question_idx"])

# Data-capture check: a successful API call whose stored content is empty
# means the model's answer text was not captured (cf. the archived max_tokens=50
# run, where reasoning-mode models consumed the whole budget and returned empty
# content). Report loudly; do not treat empty responses as genuine refusals.
empty_raw = {m: sum(1 for r in by_model[m] if not r["raw_response"])
             for m in MODEL_ORDER}
if any(empty_raw.values()):
    print("[!!] DATA-CAPTURE WARNING: empty raw_response rows present per "
          f"model: { {m: c for m, c in empty_raw.items() if c} } -- scores for "
          "those models are NOT interpretable as knowledge (see protocol fix "
          "note; broken max_tokens=50 run archived as v2_max50_provenance.jsonl)")

# ----------------------------------------------------------------------------
# 1. Main results
# ----------------------------------------------------------------------------
strict_scores = {}    # model -> (correct, total)
for m in MODEL_ORDER:
    rs = by_model[m]
    strict_scores[m] = (sum(1 for r in rs if r["predicted_idx"] == r["correct_idx"]),
                        len(rs))

wilson = {}
for m in MODEL_ORDER:
    corr, tot = strict_scores[m]
    lo, hi = wilson_ci(corr, tot)
    wilson[m] = {"score_pct": round(100.0 * corr / tot, 2),
                 "ci_low": round(100.0 * lo, 2), "ci_high": round(100.0 * hi, 2),
                 "n_correct": corr, "n_total": tot}

# per-dimension matrix: dimension x model (7 x 8)
dimensions = sorted({r["dimension"] for r in rows})
per_dim_model = {d: {} for d in dimensions}
per_dim_totals = {d: {m: 0 for m in MODEL_ORDER} for d in dimensions}
for m in MODEL_ORDER:
    for r in by_model[m]:
        per_dim_totals[r["dimension"]][m] += 1
        if r["predicted_idx"] == r["correct_idx"]:
            per_dim_model[r["dimension"]][m] = per_dim_model[r["dimension"]].get(m, 0) + 1
per_dimension = {d: {m: round(100.0 * per_dim_model[d].get(m, 0)
                              / max(per_dim_totals[d][m], 1), 2)
                     for m in MODEL_ORDER} for d in dimensions}

# per-tier matrix: tier x model (5 x 8)
tiers = sorted({r["difficulty"] for r in rows})
per_tier_model = {t: {} for t in tiers}
for m in MODEL_ORDER:
    for r in by_model[m]:
        per_tier_model[r["difficulty"]][m] = per_tier_model[r["difficulty"]].get(m, 0) + (
            r["predicted_idx"] == r["correct_idx"])
per_tier_n = {t: sum(1 for r in rows if r["difficulty"] == t) // len(MODEL_ORDER)
              for t in tiers}  # items per tier (rows span all 8 models equally)
per_tier = {t: {m: round(100.0 * per_tier_model[t][m] / per_tier_n[t], 2)
                for m in MODEL_ORDER} for t in tiers}

# ----------------------------------------------------------------------------
# 2. Original-vs-new split
# ----------------------------------------------------------------------------
split = {}
for part, lo, hi in (("original_210", 0, N_ORIGINAL), ("new_40", N_ORIGINAL, N_ITEMS)):
    scores = {}
    for m in MODEL_ORDER:
        rs = [r for r in by_model[m] if lo <= r["question_idx"] < hi]
        corr = sum(1 for r in rs if r["predicted_idx"] == r["correct_idx"])
        scores[m] = {"correct": corr, "total": len(rs),
                     "accuracy_pct": round(100.0 * corr / len(rs), 2)}
        wl = wilson_ci(corr, len(rs))
        scores[m]["ci_low"] = round(100.0 * wl[0], 2)
        scores[m]["ci_high"] = round(100.0 * wl[1], 2)
    split[part] = scores

# per-tier detail for the new 40 (30 T4 + 10 T5)
split["new_40_per_tier"] = {}
for t in (4, 5):
    row = {}
    for m in MODEL_ORDER:
        rs = [r for r in by_model[m]
              if N_ORIGINAL <= r["question_idx"] < N_ITEMS and r["difficulty"] == t]
        corr = sum(1 for r in rs if r["predicted_idx"] == r["correct_idx"])
        row[m] = {"correct": corr, "total": len(rs),
                  "accuracy_pct": round(100.0 * corr / len(rs), 2)
                  if rs else None}
    split["new_40_per_tier"][str(t)] = row

# ----------------------------------------------------------------------------
# 3. Parsing robustness + error taxonomy
# ----------------------------------------------------------------------------
PARSERS = {"P_strict": strict_recorded_parser, "P_first": parse_first,
           "P_last": parse_last, "P_any": parse_any}
parsers_table = {p: {} for p in PARSERS}
for pname, fn in PARSERS.items():
    for m in MODEL_ORDER:
        rs = by_model[m]
        if pname == "P_strict":
            corr, tot = strict_scores[m]     # recorded pipeline result (full text)
        else:
            corr = sum(1 for r in rs if fn(r["raw_response"]) == r["correct_idx"])
            tot = len(rs)
        parsers_table[pname][m] = {"correct": corr, "total": tot,
                                   "accuracy_pct": round(100.0 * corr / tot, 2)}

# replication check: recorded predicted_idx vs replica on stored (300-char) text
rep_mismatch = []
for m in MODEL_ORDER:
    for r in by_model[m]:
        rep = strict_recorded_parser(r["raw_response"])
        if rep != r["predicted_idx"]:
            rep_mismatch.append((m, r["question_idx"], r["predicted_idx"], rep,
                                 len(r["raw_response"])))
rep_agree = 100.0 * (EXPECTED_TOTAL_ROWS - len(rep_mismatch)) / EXPECTED_TOTAL_ROWS
if rep_agree < 95.0:
    failures.append(f"strict replica agreement on stored text = {rep_agree:.2f}% < 95%")
notes.append(f"strict-parser replica agreement on stored raw_response (300-char "
             f"prefix): {rep_agree:.2f}% ({len(rep_mismatch)} mismatches; recorded "
             f"parse ran on the full response)")

# error taxonomy on recorded strict predictions
error_taxonomy = {}
format_rows = []
for m in MODEL_ORDER:
    rs = [r for r in by_model[m] if r["predicted_idx"] != r["correct_idx"]]
    fmt = [r for r in rs if r["predicted_idx"] == -1]
    wr = [r for r in rs if r["predicted_idx"] != -1]
    error_taxonomy[m] = {"format_errors": len(fmt), "wrong_letter_errors": len(wr),
                         "total_errors": len(rs)}
    format_rows.extend(fmt)

# dump every FORMAT error row
with OUT_FAILURES.open("w", encoding="utf-8") as fh:
    for r in sorted(format_rows, key=lambda r: (r["model"], r["question_idx"])):
        fh.write(json.dumps({
            "model": r["model"],
            "question_idx": r["question_idx"],
            "question": r["question"],
            "correct_idx": r["correct_idx"],
            "raw_response": r["raw_response"],
            "served_model": r["served_model"],
        }) + "\n")

# ----------------------------------------------------------------------------
# 4. McNemar (28 pairs, 250 paired items)
# ----------------------------------------------------------------------------
item_ok = {m: {r["question_idx"]: int(r["predicted_idx"] == r["correct_idx"])
               for r in by_model[m]} for m in MODEL_ORDER}
mcnemar_pairs = []
for i, ma in enumerate(MODEL_ORDER):
    for mb in MODEL_ORDER[i + 1:]:
        both_corr = both_wrong = b = c = 0
        for q in range(N_ITEMS):
            oka, okb = item_ok[ma][q], item_ok[mb][q]
            both_corr += oka & okb
            both_wrong += (1 - oka) & (1 - okb)
            b += oka & (1 - okb)
            c += (1 - oka) & okb
        p = exact_binom_two_sided(min(b, c), b + c)
        lo_a, hi_a = wilson[ma]["ci_low"] / 100.0, wilson[ma]["ci_high"] / 100.0
        lo_b, hi_b = wilson[mb]["ci_low"] / 100.0, wilson[mb]["ci_high"] / 100.0
        mcnemar_pairs.append({
            "pair": f"{ma} vs {mb}", "model_a": ma, "model_b": mb,
            "a": both_corr, "b": b, "c": c, "d": both_wrong,
            "n_discordant": b + c,
            "p_value": round(p, 12),
            "exact_or_approx": "exact" if HAS_SCIPY else "exact_manual_doubling",
            "significant_at_0.05": p < 0.05,
            "significant_at_bonferroni": p < MC_BONFERRONI,
            "ci_overlap": not (hi_a < lo_b or hi_b < lo_a),
        })
n_sig05 = sum(1 for x in mcnemar_pairs if x["significant_at_0.05"])
n_sig_bonf = sum(1 for x in mcnemar_pairs if x["significant_at_bonferroni"])

# ----------------------------------------------------------------------------
# 5. Item-level statistics
# ----------------------------------------------------------------------------
model_totals = {m: strict_scores[m][0] for m in MODEL_ORDER}
per_item = []
for q in range(N_ITEMS):
    scores = [item_ok[m][q] for m in MODEL_ORDER]
    n_corr = sum(scores)
    err = 1.0 - n_corr / len(MODEL_ORDER)
    disc = pearson_xy(scores, [model_totals[m] for m in MODEL_ORDER])
    p_corr = max(0.01, min(0.99, n_corr / len(MODEL_ORDER)))
    per_item.append({"idx": q,
                     "tier": int(by_model[MODEL_ORDER[0]][q]["difficulty"]),
                     "n_models_correct": n_corr,
                     "error_rate": round(err, 6),
                     "discrimination": None if disc is None else round(disc, 6),
                     "irt_difficulty": round(-math.log(p_corr / (1.0 - p_corr)), 6)})
n_const = sum(1 for it in per_item if it["discrimination"] is None)
if n_const:
    notes.append(f"{n_const} of {N_ITEMS} items with zero variance across the 8 "
                 f"models (all correct or all wrong) -> discrimination None")

per_tier_stats = {}
for t in tiers:
    its = [it for it in per_item if it["tier"] == t]
    disc = [it["discrimination"] for it in its if it["discrimination"] is not None]
    per_tier_stats[str(t)] = {
        "n": len(its),
        "mean_error_rate": round(sum(it["error_rate"] for it in its) / len(its), 6),
        "mean_discrimination": round(sum(disc) / len(disc), 6) if disc else None,
        "mean_irt": round(sum(it["irt_difficulty"] for it in its) / len(its), 6),
    }
highest_error_tier = max(tiers, key=lambda t: per_tier_stats[str(t)]["mean_error_rate"])

tier_vec = [float(it["tier"]) for it in per_item]
err_vec = [it["error_rate"] for it in per_item]
irt_vec = [it["irt_difficulty"] for it in per_item]
rho_te, p_te = spearman_rho(tier_vec, err_vec)
rho_ti, p_ti = spearman_rho(tier_vec, irt_vec)

# ----------------------------------------------------------------------------
# Assemble JSON
# ----------------------------------------------------------------------------
output = {
    "meta": {
        "input": str(RESULTS_JSONL),
        "n_models": 8, "n_items": N_ITEMS, "n_rows": EXPECTED_TOTAL_ROWS,
        "n_original_210": N_ORIGINAL, "n_new_40": N_NEW,
        "bank_correct_position_dist": dict(collections.Counter(
            b["correct"] for b in bank)) if bank else None,
        "scipy_available": HAS_SCIPY,
        "served_model_per_label": served,
        "ts_utc_min": ts_min, "ts_utc_max": ts_max,
        "mcnemar_method": "exact (scipy.stats.binomtest)" if HAS_SCIPY
                          else "exact manual doubling (cap 1)",
        "tokens_per_model": {
            m: {"total": sum(r["tokens"] for r in by_model[m]),
                "mean": round(sum(r["tokens"] for r in by_model[m]) / N_ITEMS, 1),
                "min": min(r["tokens"] for r in by_model[m]),
                "max": max(r["tokens"] for r in by_model[m])}
            for m in MODEL_ORDER
        },
        "token_note": "tokens = provider usage.total_tokens. On DoubleWordAI the "
                      "reasoning-mode models (Qwen-3.5-9B, Qwen-3.6-35B, Kimi-K2.6, "
                      "and intermittently DeepSeek-V4-Pro) consume tokens on "
                      "internal reasoning, so per-row tokens include reasoning "
                      "tokens for those models; token-efficiency comparisons must "
                      "not treat all 8 rows as comparable generation cost.",
    },
    "main_results": {
        "per_model": wilson,
        "per_dimension": per_dimension,
        "per_tier": per_tier,
    },
    "split_original_vs_new": split,
    "parsers": parsers_table,
    "error_taxonomy": error_taxonomy,
    "format_error_rows_dumped_to": str(OUT_FAILURES),
    "mcnemar": {
        "pairs": mcnemar_pairs,
        "bonferroni_alpha": round(MC_BONFERRONI, 6),
        "n_significant_at_0.05": n_sig05,
        "n_significant_at_bonferroni": n_sig_bonf,
    },
    "item_stats": {
        "per_tier": per_tier_stats,
        "spearman_tier_error": {"rho": round(rho_te, 6), "p": round(p_te, 12),
                                "approx": not HAS_SCIPY},
        "spearman_tier_irt": {"rho": round(rho_ti, 6), "p": round(p_ti, 12),
                              "approx": not HAS_SCIPY},
        "highest_error_tier": highest_error_tier,
        "per_question": per_item,
    },
    "sanity": {
        "rows_ok": len(rows) == EXPECTED_TOTAL_ROWS,
        "rows_per_model_ok": all(counts[m] == N_ITEMS for m in MODEL_ORDER),
        "no_error_rows": len(stale) == 0,
        "stale_error_rows_dropped": len(stale),
        "ts_utc_ok": not missing_ts,
        "no_duplicates": dupes == 0,
        "empty_raw_response_per_model": empty_raw,
        "strict_replica_agreement_pct": round(rep_agree, 2),
        "notes": notes,
    },
}
with OUT_JSON.open("w", encoding="utf-8") as fh:
    json.dump(output, fh, indent=2, ensure_ascii=False)
    fh.write("\n")

# ----------------------------------------------------------------------------
# Readable stdout
# ----------------------------------------------------------------------------
print("\n" + "=" * 78)
print("1. MAIN RESULTS (250 items) + Wilson 95% CI")
print("=" * 78)
for m in MODEL_ORDER:
    w = wilson[m]
    print(f"{m:<20s} {w['n_correct']:>3d}/250 ({w['score_pct']:>6.2f}%)  "
          f"95% CI [{w['ci_low']:>5.2f}, {w['ci_high']:>5.2f}]")

print("\nPer-dimension accuracy (%):")
dims_row = f"{'dim':>5s}" + "".join(f"{m.split('-')[0][:11]:>12s}" for m in MODEL_ORDER)
print(dims_row)
for d in dimensions:
    print(f"{d:>5s}" + "".join(f"{per_dimension[d][m]:>12.2f}" for m in MODEL_ORDER))

print("\nPer-tier accuracy (%):")
tier_row = f"{'tier':>5s}" + "".join(f"{m.split('-')[0][:11]:>12s}" for m in MODEL_ORDER)
print(tier_row)
for t in sorted(per_tier):
    print(f"T{t} (n={per_tier_n[t]}):" + "".join(f"{per_tier[t][m]:>12.2f}"
                                                 for m in MODEL_ORDER))

print("\n" + "=" * 78)
print("2. ORIGINAL 210 vs NEW 40 HARD ITEMS")
print("=" * 78)
print(f"{'model':<20s} {'orig 210':>10s} {'95% CI':>16s} | {'new 40':>10s} {'95% CI':>16s}")
for m in MODEL_ORDER:
    o = split["original_210"][m]
    n_ = split["new_40"][m]
    print(f"{m:<20s} {o['accuracy_pct']:>9.2f}% [{o['ci_low']:>6.2f},{o['ci_high']:>6.2f}] | "
          f"{n_['accuracy_pct']:>9.2f}% [{n_['ci_low']:>6.2f},{n_['ci_high']:>6.2f}]")
for t in ("4", "5"):
    print(f"\nNew-40 tier T{t} accuracy (n per model):")
    for m in MODEL_ORDER:
        v = split["new_40_per_tier"][t][m]
        print(f"  {m:<20s} {v['accuracy_pct']:>7.2f}%  ({v['correct']}/{v['total']})")

print("\n" + "=" * 78)
print("3. PARSER ROBUSTNESS + ERROR TAXONOMY")
print("=" * 78)
hdr = f"{'model':<20s}" + "".join(f"{p:>10s}" for p in PARSERS) + f"{'errors':>8s}"
print(hdr + f"{'format':>8s}{'wrong':>7s}")
for m in MODEL_ORDER:
    e = error_taxonomy[m]
    line = f"{m:<20s}"
    for p in PARSERS:
        line += f"{parsers_table[p][m]['accuracy_pct']:>10.2f}"
    line += f"{e['total_errors']:>8d}{e['format_errors']:>8d}{e['wrong_letter_errors']:>7d}"
    print(line)
print(f"Strict-parser replica agreement on stored text: {rep_agree:.2f}% "
      f"({len(rep_mismatch)} mismatches)")
print(f"Wrote {len(format_rows)} FORMAT-error rows to {OUT_FAILURES.name}")

print("\n" + "=" * 78)
print("4. MCNEMAR (28 pairs, 250 paired items)")
print("=" * 78)
print(f"Significant: {n_sig05}/28 at alpha=0.05; {n_sig_bonf}/28 at Bonferroni "
      f"{MC_BONFERRONI:.4f} (method: "
      f"{'scipy exact' if HAS_SCIPY else 'manual exact doubling'})")
for x in mcnemar_pairs:
    if x["significant_at_0.05"]:
        print(f"  sig(0.05) {'sig(0.0018)' if x['significant_at_bonferroni'] else '          '} "
              f"{x['pair']:<52s} b={x['b']:>2d} c={x['c']:>2d} p={x['p_value']:.2e} "
              f"CIoverlap={x['ci_overlap']}")

print("\n" + "=" * 78)
print("5. ITEM-LEVEL STATISTICS / DIFFICULTY VALIDATION (250 items)")
print("=" * 78)
print(f"{'tier':>5s} {'n':>5s} {'mean_err':>10s} {'mean_disc':>10s} {'mean_irt':>10s}")
for t in sorted(per_tier_stats, key=int):
    v = per_tier_stats[t]
    disc = "n/a" if v["mean_discrimination"] is None else f"{v['mean_discrimination']:.4f}"
    print(f"T{t:>4s} {v['n']:>5d} {v['mean_error_rate']:>10.4f} {disc:>10s} "
          f"{v['mean_irt']:>10.3f}")
print(f"\nSpearman(tier, error rate): rho={rho_te:.4f}, p={p_te:.2e}")
print(f"Spearman(tier, IRT):        rho={rho_ti:.4f}, p={p_ti:.2e}")
print(f"Highest mean error tier: T{highest_error_tier}")

print("\n" + "=" * 78)
print("6. SANITY / PROVENANCE")
print("=" * 78)
for m in MODEL_ORDER:
    print(f"served_model[{m}] = {served[m][0]}")
print(f"ts_utc window: {ts_min}  ->  {ts_max}")
print(f"rows={len(rows)} (expected {EXPECTED_TOTAL_ROWS}); per-model "
      f"{dict(counts)}; stale ERROR rows dropped={len(stale)}; missing ts_utc="
      f"{len(missing_ts)}; duplicates={dupes}")
print(f"replica agreement: {rep_agree:.2f}%")
for n_ in notes:
    print("note:", n_)
print(f"\nWrote {OUT_JSON.name} and {OUT_FAILURES.name}")
