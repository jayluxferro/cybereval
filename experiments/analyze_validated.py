#!/usr/bin/env python3
"""Round-2 validated analysis on the single-day full re-run.

Input:  tmp/recapture/full_run.jsonl (8 models x 250 items, one measurement
        day, complete response capture: content + reasoning_content +
        finish_reason).
Output: tmp/recapture/round2_docket.jsonl
        tmp/recapture/round2_validated_answers.json
        tmp/recapture/round2_summary.txt

Parsers (on the content channel, raw_full -- the same channel the original
protocol parsed): strict_recorded (verbatim copy), first, last, any.

Pre-registered adjudication rubric (identical to build_docket.py):
  R1. `</think>` present -> final answer = LAST standalone A-D letter AFTER the
      last `</think>`. Letters inside reasoning blocks are extraction noise.
      None after the marker -> FORMAT.
  R2. No marker, single letter -> that letter.
  R3. No marker, multiple letters -> last standalone letter.
  R4. Empty content -> FORMAT (generation-budget exhaustion; corroborated by
      finish_reason == "length" with non-empty reasoning_content).

Verdicts: EXTRACTION / KNOWLEDGE / FORMAT / CLEAN.
Borderline flags for author sign-off: CONFLICT, NO_FINAL, BUDGET, AMBIGUOUS.
"""

import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

def _locate(name):
    """Locate a data file in the repo layout (experiments/results/round2_validated/)
    or the release layout (scripts/ + data/round2_validated/)."""
    candidates = [
        HERE / "results" / "round2_validated" / name,          # repo: experiments/
        HERE.parent / "data" / "round2_validated" / name,      # release: scripts/
        HERE / name,                                            # same-dir (original)
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"{name} not found; checked {candidates}")

FULL_RUN = _locate("full_run.jsonl")
DOCKET = Path(_locate("docket.jsonl"))
VALIDATED = Path(_locate("validated_answers.json"))
SUMMARY = Path(_locate("summary.txt"))
_bank_candidates = [HERE / "results" / "question_bank.json",      # repo: experiments/results/
                    HERE.parent / "data" / "question_bank.json"]  # release: data/
BANK = next((c for c in _bank_candidates if c.exists()), _bank_candidates[0])

MODEL_ORDER = [
    "Kimi-K2.6", "Claude-Sonnet-4.6", "Gemma-4-31B", "DeepSeek-V4-Pro",
    "Qwen-3.5-9B", "DeepSeek-V4-Flash", "Qwen-3.6-35B", "Nemotron-Super-120B",
]

LETTER = r"[A-Da-d]"

def standalone(text):
    return re.findall(rf"\b({LETTER})\b", text or "")

def last_letter(text):
    ls = standalone(text)
    return ord(ls[-1].upper()) - ord("A") if ls else -1

def first_letter(text):
    m = re.search(rf"\b({LETTER})\b", text or "")
    return ord(m.group(1).upper()) - ord("A") if m else -1

def any_letter(text):
    m = re.search(LETTER, text or "")
    return ord(m.group(0).upper()) - ord("A") if m else -1

def strict_recorded(text):
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

def think_split(text):
    idx = (text or "").lower().rfind("</think>")
    if idx < 0:
        return (text or ""), ""
    return text[:idx], text[idx + len("</think>"):]

def adjudicate(raw_full, reasoning_full):
    flags = []
    if not raw_full.strip():
        if reasoning_full.strip():
            flags.append("BUDGET")
        return -1, -1, flags
    before, after = think_split(raw_full)
    if after.strip():
        post = last_letter(after)
        if post == -1:
            return -1, last_letter(before), flags + ["NO_FINAL"]
        rl = last_letter(before)
        if rl != -1 and rl != post:
            flags.append("CONFLICT")
        return post, rl, flags
    stripped = re.sub(r"[\s\.\!\)\]\>]*$", "", raw_full.strip())
    if re.fullmatch(rf"{LETTER}", stripped, re.IGNORECASE):
        return ord(stripped.upper()) - ord("A"), -1, flags
    return last_letter(raw_full), -1, flags

def wilson_ci(k, n, z=1.96):
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)

def main():
    rows = [json.loads(l) for l in FULL_RUN.open(encoding="utf-8") if l.strip()]
    # dedupe: last non-ERROR row per key
    best = {}
    for r in rows:
        if not r.get("raw_full", "").startswith("ERROR:"):
            best[(r["model"], r["question_idx"])] = r
    rows = sorted(best.values(), key=lambda r: (r["model"], r["question_idx"]))
    n_err = sum(1 for r in rows if r.get("raw_full", "").startswith("ERROR:"))
    print(f"clean rows: {len(rows)} (expected 2000)")
    if len(rows) != 2000 or n_err:
        print(f"[!!] missing rows or {n_err} ERROR rows remain -- rerun "
              f"run_full_recapture.py before analyzing")
        sys.exit(1)

    from scipy import stats as st
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    docket = []
    validated = {}
    out = []

    for r in rows:
        m, q = r["model"], r["question_idx"]
        text = r["raw_full"]
        s = strict_recorded(text)
        f = first_letter(text)
        l = last_letter(text)
        a = any_letter(text)
        adj, rl, flags = adjudicate(text, r.get("reasoning_full", ""))
        validated[f"{m}|{q}"] = {
            "model": m, "question_idx": q, "correct_idx": r["correct_idx"],
            "adjudicated": adj, "recorded_strict": s,
            "finish_reason": r.get("finish_reason"), "flags": flags,
            "extractors": {"strict": s, "first": f, "last": l, "any": a},
        }
        vals = {s, f, l, a}
        if len(vals) > 1 or flags:
            verdict = ("FORMAT" if adj == -1
                       else ("EXTRACTION" if adj == r["correct_idx"] else "KNOWLEDGE"))
            docket.append({
                "model": m, "question_idx": q, "tier": r["difficulty"],
                "dimension": r["dimension"], "correct_idx": r["correct_idx"],
                "strict": s, "first": f, "last": l, "any": a,
                "adjudicated": adj, "reasoning_last": rl, "verdict": verdict,
                "flags": flags, "finish_reason": r.get("finish_reason"),
                "raw_len": r["raw_len"], "reasoning_len": r["reasoning_len"],
                "text": text if len(text) <= 240 else text[-240:],
                "bank_choices": bank[q]["choices"],
            })

    DOCKET.write_text("\n".join(json.dumps(d) for d in docket) + "\n", encoding="utf-8")
    VALIDATED.write_text(json.dumps(validated, indent=2), encoding="utf-8")

    vc = defaultdict(int)
    for d in docket:
        vc[d["verdict"]] += 1
    fc = defaultdict(int)
    for d in docket:
        for fl in d["flags"]:
            fc[fl] += 1
    out.append(f"docket rows: {len(docket)} | verdicts: {dict(vc)} | flags: {dict(fc)}")
    out.append("")
    out.append(f"{'model':<20s} {'strict':>9s} {'adjud':>9s} {'ci(adjud)':>18s} {'delta':>6s}")
    per_model = {m: [r for r in rows if r["model"] == m] for m in MODEL_ORDER}
    for m in MODEL_ORDER:
        rs = per_model[m]
        strict_c = sum(1 for r in rs if r["predicted_idx"] == r["correct_idx"])
        adj_c = sum(1 for r in rs if validated[f"{m}|{r['question_idx']}"]["adjudicated"] == r["correct_idx"])
        lo, hi = wilson_ci(adj_c, len(rs))
        delta = sum(1 for r in rs if validated[f"{m}|{r['question_idx']}"]["adjudicated"] != r["predicted_idx"])
        out.append(f"{m:<20s} {strict_c:>4d}/250 {adj_c:>4d}/250 "
                   f"({100*lo:.2f}-{100*hi:.2f})% {delta:>6d}")
    out.append("")

    out.append("McNemar on adjudicated answers (exact binomial, two-sided):")
    sig = []
    for i in range(len(MODEL_ORDER)):
        for j in range(i + 1, len(MODEL_ORDER)):
            m1, m2 = MODEL_ORDER[i], MODEL_ORDER[j]
            qs = sorted({r["question_idx"] for r in per_model[m1]})
            b = c = 0
            for q_ in qs:
                a1 = validated[f"{m1}|{q_}"]["adjudicated"] == bank[q_]["correct"]
                a2 = validated[f"{m2}|{q_}"]["adjudicated"] == bank[q_]["correct"]
                if a1 and not a2:
                    b += 1
                elif a2 and not a1:
                    c += 1
            n = b + c
            p = 1.0 if n == 0 else float(st.binomtest(min(b, c), n, 0.5,
                                                      alternative="two-sided").pvalue)
            if p < 0.05:
                sig.append((p, m1, m2, b, c, n))
    if sig:
        for p, m1, m2, b, c, n in sorted(sig):
            out.append(f"  {m1} vs {m2}: b={b} c={c} n={n} p={p:.4g} SIG")
    else:
        out.append("  none significant at alpha=0.05 (all 28 pairs)")
    out.append("")

    tiers = defaultdict(lambda: [0, 0])
    for r in rows:
        t = tiers[r["difficulty"]]
        t[1] += 1
        if validated[f"{r['model']}|{r['question_idx']}"]["adjudicated"] != r["correct_idx"]:
            t[0] += 1
    out.append("per-tier error rates (adjudicated):")
    for t in sorted(tiers):
        e, n = tiers[t]
        out.append(f"  T{t}: {e}/{n} = {100*e/n:.2f}%")

    # Spearman tier vs per-item adjudicated error rate
    err_rate = {}
    for r in rows:
        k = r["question_idx"]
        err_rate.setdefault(k, [0, 0, r["difficulty"]])  # err, n, tier
        err_rate[k][1] += 1
        if validated[f"{r['model']}|{r['question_idx']}"]["adjudicated"] != r["correct_idx"]:
            err_rate[k][0] += 1
    tiers_x = [v[2] for v in err_rate.values()]
    rates_y = [v[0] / v[1] for v in err_rate.values()]
    rho, p = st.spearmanr(tiers_x, rates_y)
    out.append(f"Spearman(tier, adjudicated error rate): rho={rho:.4f} p={p:.3g} (n={len(rates_y)} items)")

    # hard-tail split (original 210 vs new 40) on adjudicated
    for part, lo, hi in (("original_210", 0, 210), ("new_40", 210, 250)):
        out.append(f"{part} (adjudicated):")
        for m in MODEL_ORDER:
            rs = [r for r in per_model[m] if lo <= r["question_idx"] < hi]
            c_ = sum(1 for r in rs if validated[f"{m}|{r['question_idx']}"]["adjudicated"] == r["correct_idx"])
            out.append(f"  {m:<20s} {c_:>3d}/{len(rs)}")

    # per-item IRT logit difficulty and point-biserial discrimination
    import math
    item_stats = {}
    items = defaultdict(list)
    for r in rows:
        items[r["question_idx"]].append((r["model"], validated[f"{r['model']}|{r['question_idx']}"]["adjudicated"] == r["correct_idx"]))
    model_totals = {}
    for m in MODEL_ORDER:
        rs = [r for r in rows if r["model"] == m]
        model_totals[m] = sum(1 for r in rs if validated[f"{m}|{r['question_idx']}"]["adjudicated"] == r["correct_idx"])
    for q, pairs in sorted(items.items()):
        p = sum(1 for _, ok in pairs if ok) / len(pairs)
        pc = min(max(p, 0.01), 0.99)
        d = -math.log(pc / (1 - pc))
        xs = [1.0 if ok else 0.0 for _, ok in pairs]
        ys = [float(model_totals[m]) for m, _ in pairs]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
        vx = sum((x - mx) ** 2 for x in xs) / n
        vy = sum((y - my) ** 2 for y in ys) / n
        item_stats[q] = {
            "tier": next(r["difficulty"] for r in rows if r["question_idx"] == q),
            "error_rate": 1.0 - p,
            "irt_logit_difficulty": round(d, 6),
            "point_biserial": round(cov / math.sqrt(vx * vy), 6) if vx * vy > 0 else 0.0,
        }
    (SUMMARY.parent / "item_stats.json").write_text(json.dumps(item_stats, indent=2), encoding="utf-8")

    SUMMARY.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))

if __name__ == "__main__":
    main()
