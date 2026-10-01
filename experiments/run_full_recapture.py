#!/usr/bin/env python3
"""Full re-run with complete response capture (round-2 validated dataset).

Why: the adjudicated score set must derive from a single measurement day.
The Sept-8 v2 run stored 300-char prefixes; the 93-row re-capture pass mixes
measurement days into any 'validated' set. This script re-runs ALL 8 models x
250 items (2,000 calls) with full-response capture:
  - content            (the answer channel; parsed per protocol)
  - reasoning_content  (evidence channel; capped at 12,000 chars)
  - finish_reason      (budget-exhaustion evidence for format errors)

Prompt and parameters are copied verbatim from run_live_mcq_v2.py
(max_tokens 2048, temperature 0.0, no system prompt). Providers: DoubleWordAI
(7 models) + OpenRouter (Claude-Sonnet-4.6), same as the original run.

Idempotent on (model, question_idx); 4 retries per row with 2/4/8 s backoff.

Usage: python3 tmp/recapture/run_full_recapture.py
Output: tmp/recapture/full_run.jsonl
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] if (HERE.parents[1] / "experiments" / "results" / "question_bank.json").exists() else HERE.parent
BANK = (ROOT / "experiments/results/question_bank.json"
        if (ROOT / "experiments/results/question_bank.json").exists()
        else ROOT / "data" / "question_bank.json")
DW_KEY = Path("/Users/jay/dev/pentest/audit/doubleword.ai/dw-mcp/creds.json")
DW_API = "https://api.doubleword.ai/v1/chat/completions"
OR_API = "https://openrouter.ai/api/v1/chat/completions"
OUTPUT = Path(os.environ.get("CYBEREVAL_FULLRUN_OUTPUT", HERE / "full_run.jsonl"))

CONTENT_CAP = 6000
REASONING_CAP = 12000
RETRIES = 4
BACKOFF_S = 2.0

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


def load_keys():
    k = {}
    if DW_KEY.exists():
        k["dw"] = json.loads(DW_KEY.read_text()).get("api_key", "")
    k["or"] = os.environ.get("OPENROUTER_API_KEY", "")
    return k


def extract_answer(content):
    """Verbatim copy of run_live_mcq_v2.extract_answer (strict protocol parser)."""
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
    """Verbatim copy of run_live_mcq_v2.make_prompt."""
    letters = ["A", "B", "C", "D"]
    choices_text = "\n".join(f"  {letters[j]}. {q['choices'][j]}" for j in range(4))
    return ("Cybersecurity MCQ. Choose the BEST answer. Reply with ONLY the letter (A, B, C, or D).\n\n"
            "Question: " + q["question"] + "\n\nOptions:\n" + choices_text +
            "\n\nYour answer (single letter):")


def main():
    keys = load_keys()
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    print(f"Bank: {len(bank)} | Models: {len(MODELS)} | Calls: {len(bank)*len(MODELS)}")
    print(f"DW: {'yes' if keys.get('dw') else 'NO'} | OR: {'yes' if keys.get('or') else 'NO'}")

    seen = set()
    if OUTPUT.exists():
        for line in OUTPUT.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not row.get("raw_full", "").startswith("ERROR:"):
                seen.add((row["model"], row["question_idx"]))

    total = len(bank) * len(MODELS)
    done = 0
    start = time.time()

    async def process(q, i, model):
        nonlocal done
        if (model["label"], i) in seen:
            done += 1
            return
        api_key = keys.get(model["provider"], "")
        if not api_key:
            print(f"[!!] no key for {model['provider']} ({model['label']})")
            return
        url = DW_API if model["provider"] == "dw" else OR_API
        headers = {"Authorization": f"Bearer {api_key}",
                   "Content-Type": "application/json"}
        payload = {"model": model["id"],
                   "messages": [{"role": "user", "content": make_prompt(q)}],
                   "max_tokens": 2048, "temperature": 0.0}
        ts = datetime.now(timezone.utc).isoformat()
        last_exc = None
        for attempt in range(1, RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=60, trust_env=False) as c:
                    resp = await c.post(url, json=payload, headers=headers, timeout=60)
                resp.raise_for_status()
                d = resp.json()
                msg = d.get("choices", [{}])[0].get("message", {})
                content = msg.get("content") or ""
                reasoning = (msg.get("reasoning_content")
                             or msg.get("reasoning") or "")
                result = {
                    "model": model["label"], "question_idx": i,
                    "question": q["question"], "correct_idx": q["correct"],
                    "difficulty": q["difficulty"], "dimension": q["dimension"],
                    "predicted_idx": extract_answer(content),
                    "correct": extract_answer(content) == q["correct"],
                    "raw_full": content[:CONTENT_CAP],
                    "raw_len": len(content),
                    "truncated_at": CONTENT_CAP if len(content) > CONTENT_CAP else None,
                    "reasoning_full": reasoning[:REASONING_CAP],
                    "reasoning_len": len(reasoning),
                    "finish_reason": d.get("choices", [{}])[0].get("finish_reason"),
                    "tokens": d.get("usage", {}).get("total_tokens", 0),
                    "served_model": d.get("model", ""),
                    "ts_utc": ts, "attempts": attempt,
                }
                OUTPUT.open("a", encoding="utf-8").write(json.dumps(result) + "\n")
                break
            except Exception as exc:
                last_exc = exc
                if attempt < RETRIES:
                    time.sleep(BACKOFF_S * (2 ** (attempt - 1)))
        else:
            result = {"model": model["label"], "question_idx": i,
                      "correct_idx": q["correct"], "predicted_idx": -1,
                      "correct": False, "difficulty": q["difficulty"],
                      "dimension": q["dimension"],
                      "raw_full": f"ERROR: {str(last_exc)[:100]}", "raw_len": 0,
                      "truncated_at": None, "reasoning_full": "",
                      "reasoning_len": 0, "finish_reason": "error",
                      "tokens": 0, "served_model": "", "ts_utc": ts,
                      "attempts": RETRIES}
            OUTPUT.open("a", encoding="utf-8").write(json.dumps(result) + "\n")
        done += 1
        if done % 200 == 0 or done == total:
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate / 60 if rate > 0 else 0
            print(f"  [{done}/{total}] rate={rate:.1f}/s ETA={eta:.1f}min", flush=True)

    async def run_all():
        sem = asyncio.Semaphore(8)
        tasks = []
        for i, q in enumerate(bank):
            for model in MODELS:
                async def wrapped(q=q, i=i, model=model):
                    async with sem:
                        await process(q, i, model)
                tasks.append(wrapped())
        await asyncio.gather(*tasks)

    asyncio.run(run_all())
    print(f"Done: {done}/{total} in {(time.time()-start)/60:.1f}min")


if __name__ == "__main__":
    main()
