#!/usr/bin/env python3
"""CyberEval Live MCQ Evaluation — Tier 4/5 expansion (ARRAY revision).

Evaluates the 40 new Tier 4/5 questions against the same 8 models, using the same
endpoints and payload as run_live_mcq.py (temperature 0.0, max_tokens 50, no system
prompt), and additionally logs a UTC timestamp per call for reproducibility reporting.

Usage: python experiments/run_live_mcq_t45.py
Output: experiments/results/live_mcq/t45_results.jsonl
"""

import asyncio, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

from t45_questions import build  # noqa: E402

DW_KEY = Path("/Users/jay/dev/pentest/audit/doubleword.ai/dw-mcp/creds.json")
DW_API = "https://api.doubleword.ai/v1/chat/completions"
OR_API = "https://openrouter.ai/api/v1/chat/completions"
RESULTS_DIR = ROOT / "experiments/results/live_mcq"
OUTPUT = RESULTS_DIR / "t45_results.jsonl"

MODELS = [
    {"provider": "dw", "id": "deepseek-ai/DeepSeek-V4-Pro", "label": "DeepSeek-V4-Pro"},
    {"provider": "dw", "id": "deepseek-ai/DeepSeek-V4-Flash", "label": "DeepSeek-V4-Flash"},
    {"provider": "dw", "id": "moonshotai/Kimi-K2.6", "label": "Kimi-K2.6"},
    {"provider": "dw", "id": "Qwen/Qwen3.6-35B-A3B-FP8", "label": "Qwen-3.6-35B"},
    {"provider": "dw", "id": "Qwen/Qwen3.5-9B", "label": "Qwen-3.5-9B"},
    {"provider": "dw", "id": "google/gemma-4-31B-it", "label": "Gemma-4-31B"},
    {"provider": "dw", "id": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4", "label": "Nemotron-Super-120B"},
    {"provider": "or", "id": "anthropic/claude-sonnet-4-6", "label": "Claude-Sonnet-4.6"},
]

# Fallback routing via OpenRouter for models also listed there (used when the
# DoubleWordAI account is unavailable). Nemotron-Super-120B has no OpenRouter
# equivalent and is excluded from this set.
MODELS_OR_FALLBACK = [
    {"provider": "or", "id": "deepseek/deepseek-v4-pro", "label": "DeepSeek-V4-Pro"},
    {"provider": "or", "id": "deepseek/deepseek-v4-flash-0731", "label": "DeepSeek-V4-Flash"},
    {"provider": "or", "id": "moonshotai/kimi-k2.6", "label": "Kimi-K2.6"},
    {"provider": "or", "id": "qwen/qwen3.6-35b-a3b", "label": "Qwen-3.6-35B"},
    {"provider": "or", "id": "qwen/qwen3.5-9b", "label": "Qwen-3.5-9B"},
    {"provider": "or", "id": "google/gemma-4-31b-it", "label": "Gemma-4-31B"},
    {"provider": "or", "id": "anthropic/claude-sonnet-4-6", "label": "Claude-Sonnet-4.6"},
]


def load_keys():
    k = {}
    if DW_KEY.exists():
        k["dw"] = json.loads(DW_KEY.read_text()).get("api_key", "")
    k["or"] = os.environ.get("OPENROUTER_API_KEY", "")
    return k


def extract_answer(content):
    """Same conservative extraction as run_live_mcq.py: answer-patterns, then last standalone A-D."""
    text = content.strip()
    for pat in [r'\b([A-D])\b', r'answer\s*(?:is|:)\s*([A-D])', r'option\s*([A-D])',
                r'correct\s*(?:answer|choice|option)\s*(?:is|:)?\s*([A-D])']:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return ord(m.group(1).upper()) - ord('A')
    letters = re.findall(r'\b([A-D])\b', text)
    if letters:
        return ord(letters[-1].upper()) - ord('A')
    return -1


def make_prompt(q):
    letters = ["A", "B", "C", "D"]
    choices_text = "\n".join(f"  {letters[j]}. {q['choices'][j]}" for j in range(4))
    return ("Cybersecurity MCQ. Choose the BEST answer. Reply with ONLY the letter (A, B, C, or D).\n\n"
            "Question: " + q["question"] + "\n\nOptions:\n" + choices_text +
            "\n\nYour answer (single letter):")


async def main():
    keys = load_keys()
    modelset = os.environ.get("CYBEREVAL_MODELSET", "dw")
    models = MODELS_OR_FALLBACK if modelset == "or" else MODELS
    questions = build()
    print(f"Questions: {len(questions)} | Models: {len(models)} | Total calls: {len(questions) * len(models)}")
    print(f"DW: {'yes' if keys.get('dw') else 'NO'} | OR: {'yes' if keys.get('or') else 'NO'}")

    sem = asyncio.Semaphore(8)
    done = 0
    total = len(questions) * len(models)
    start = time.time()

    # Skip already-recorded (model, question) pairs so re-runs are idempotent.
    # Failed rows (raw_response starting with "ERROR:") are NOT counted as done
    # and will be retried on the next run.
    seen = set()
    if OUTPUT.exists():
        for line in OUTPUT.read_text().splitlines():
            row = json.loads(line)
            if not row.get("raw_response", "").startswith("ERROR:"):
                seen.add((row["model"], row["question_idx"]))

    out_f = OUTPUT.open("a")

    async def process(q, i, model):
        nonlocal done
        async with sem:
            if (model["label"], i) in seen:
                done += 1
                return
            api_key = keys.get(model["provider"], "")
            if not api_key:
                done += 1
                return
            url = DW_API if model["provider"] == "dw" else OR_API
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model["id"],
                "messages": [{"role": "user", "content": make_prompt(q)}],
                "max_tokens": 50, "temperature": 0.0,
            }
            ts = datetime.now(timezone.utc).isoformat()
            try:
                async with httpx.AsyncClient(timeout=60, trust_env=False) as c:
                    r = await c.post(url, json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                d = r.json()
                msg = d.get("choices", [{}])[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning") or ""
                answer_idx = extract_answer(content)
                correct = answer_idx == q["correct"]
                usage = d.get("usage", {})
                result = {
                    "model": model["label"], "question_idx": 210 + i,
                    "question": q["question"], "correct_idx": q["correct"],
                    "difficulty": q["difficulty"], "dimension": q["dimension"],
                    "predicted_idx": answer_idx, "correct": correct,
                    "raw_response": content[:300],
                    "tokens": usage.get("total_tokens", 0),
                    "ts_utc": ts,
                }
                out_f.write(json.dumps(result) + "\n")
                out_f.flush()
            except Exception as exc:
                result = {
                    "model": model["label"], "question_idx": 210 + i,
                    "correct_idx": q["correct"], "predicted_idx": -1, "correct": False,
                    "difficulty": q["difficulty"], "dimension": q["dimension"],
                    "raw_response": f"ERROR: {str(exc)[:100]}", "tokens": 0,
                    "ts_utc": ts,
                }
                out_f.write(json.dumps(result) + "\n")

            done += 1
            if done % 40 == 0:
                elapsed = time.time() - start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate / 60 if rate > 0 else 0
                print(f"  [{done}/{total}] rate={rate:.1f}/s ETA={eta:.1f}min", flush=True)

    tasks = [process(q, i, model) for i, q in enumerate(questions) for model in models]
    await asyncio.gather(*tasks)
    out_f.close()

    elapsed = time.time() - start
    print(f"\nDone: {done} evaluations in {elapsed/60:.1f}min")

    # Print scores over the new bank only.
    results = [json.loads(l) for l in OUTPUT.read_text().splitlines() if l.strip()]
    model_scores = {}
    for r in results:
        m = r["model"]
        model_scores.setdefault(m, {"correct": 0, "total": 0})
        model_scores[m]["total"] += 1
        if r["correct"]:
            model_scores[m]["correct"] += 1
    print(f"\n{'Model':<20s} {'Score (new 40)':>15s}")
    print("-" * 36)
    for m in sorted(model_scores, key=lambda m: model_scores[m]["correct"]/max(model_scores[m]["total"],1), reverse=True):
        s = model_scores[m]
        print(f"{m:<20s} {s['correct']}/{s['total']} ({s['correct']/max(s['total'],1)*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
