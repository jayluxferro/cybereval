#!/usr/bin/env python3
"""CyberEval Live MCQ Evaluation — parse question bank, send to real models, score answers.

Usage: python experiments/run_live_mcq.py
"""

import asyncio, json, os, re, sys, time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DW_KEY = Path("/Users/jay/dev/pentest/audit/doubleword.ai/dw-mcp/creds.json")
DW_API = "https://api.doubleword.ai/v1/chat/completions"
OR_API = "https://openrouter.ai/api/v1/chat/completions"
RESULTS_DIR = ROOT / "experiments/results/live_mcq"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    {"provider": "dw", "id": "deepseek-ai/DeepSeek-V4-Pro", "label": "DeepSeek-V4-Pro"},
    {"provider": "dw", "id": "deepseek-ai/DeepSeek-V4-Flash", "label": "DeepSeek-V4-Flash"},
    {"provider": "dw", "id": "moonshotai/Kimi-K2.6", "label": "Kimi-K2.6"},
    {"provider": "dw", "id": "Qwen/Qwen3.6-35B-A3B-FP8", "label": "Qwen-35B"},
    {"provider": "dw", "id": "Qwen/Qwen3.5-9B", "label": "Qwen-9B"},
    {"provider": "dw", "id": "google/gemma-4-31B-it", "label": "Gemma-4-31B"},
    {"provider": "dw", "id": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4", "label": "Nemotron-120B"},
    {"provider": "or", "id": "anthropic/claude-sonnet-4-6", "label": "Claude-Sonnet-4.6"},
]

# Parse questions from run_real_evaluation.py
def parse_question_bank():
    """Extract all MCQ questions from the evaluator source.

    Handles both single-line and multi-line tuple formats.
    Each question tuple: (\"question\", [\"A\",\"B\",\"C\",\"D\"], correct_idx, difficulty)
    """
    src = (ROOT / "experiments/run_real_evaluation.py").read_text()

    # Normalize: collapse multi-line tuples to single lines
    normalized = re.sub(r'\s+', ' ', src)

    questions = []
    # Match: ("question", ["A", "B", "C", "D"], int_idx, int_diff, optional_comma)
    pattern = re.compile(
        r'\(\s*"([^"]+)"\s*,\s*\[([^\]]+)\]\s*,\s*(\d+)\s*,\s*(\d+)\s*,?\s*\)'
    )

    for match in pattern.finditer(normalized):
        choices_str = match.group(2)
        # Parse individual choices
        choices = re.findall(r'"([^"]*)"', choices_str)
        if len(choices) == 4:
            questions.append({
                "question": match.group(1),
                "choices": choices,
                "correct_idx": int(match.group(3)),
                "difficulty": int(match.group(4)),
            })

    return questions


def load_keys():
    k = {}
    if DW_KEY.exists():
        k["dw"] = json.loads(DW_KEY.read_text()).get("api_key", "")
    k["or"] = os.environ.get("OPENROUTER_API_KEY", "")
    return k


def extract_answer(content):
    """Extract the model's chosen answer (A/B/C/D or 0/1/2/3 or the answer text)."""
    text = content.strip()
    # Try "Answer: A" or "The answer is A" patterns
    for pat in [r'\b([A-D])\b', r'answer\s*(?:is|:)\s*([A-D])', r'option\s*([A-D])',
                r'correct\s*(?:answer|choice|option)\s*(?:is|:)?\s*([A-D])']:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return ord(m.group(1).upper()) - ord('A')
    # Try to find the answer text in choices
    # Fall back to last single letter A-D in the response
    letters = re.findall(r'\b([A-D])\b', text)
    if letters:
        return ord(letters[-1].upper()) - ord('A')
    return -1


async def main():
    keys = load_keys()
    questions = parse_question_bank()
    print(f"Parsed {len(questions)} MCQ questions")
    print(f"Models: {len(MODELS)}")
    print(f"Total evaluations: {len(questions) * len(MODELS)}")
    print(f"DW: {'yes' if keys.get('dw') else 'NO'} | OR: {'yes' if keys.get('or') else 'NO'}")

    output_file = RESULTS_DIR / "results.jsonl"
    sem = asyncio.Semaphore(8)
    done = 0
    total = len(questions) * len(MODELS)
    start = time.time()

    out_f = open(output_file, "a")

    async def process(q, i, model):
        nonlocal done
        async with sem:
            api_key = keys.get(model["provider"], "")
            if not api_key:
                return

            letters = ["A", "B", "C", "D"]
            choices_text = "\n".join(f"  {letters[j]}. {q['choices'][j]}" for j in range(4))
            prompt = f"""Cybersecurity MCQ. Choose the BEST answer. Reply with ONLY the letter (A, B, C, or D).

Question: {q['question']}

Options:
{choices_text}

Your answer (single letter):"""

            url = DW_API if model["provider"] == "dw" else OR_API
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model["id"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 50, "temperature": 0.0,
            }

            try:
                async with httpx.AsyncClient(timeout=60, trust_env=False) as c:
                    r = await c.post(url, json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                d = r.json()
                msg = d.get("choices", [{}])[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning") or ""
                answer_idx = extract_answer(content)
                correct = answer_idx == q["correct_idx"]
                usage = d.get("usage", {})

                result = {
                    "model": model["label"], "question_idx": i,
                    "question": q["question"], "correct_idx": q["correct_idx"],
                    "difficulty": q["difficulty"],
                    "predicted_idx": answer_idx, "correct": correct,
                    "raw_response": content[:200],
                    "tokens": usage.get("total_tokens", 0),
                }
                out_f.write(json.dumps(result) + "\n")
                out_f.flush()
            except Exception as exc:
                result = {
                    "model": model["label"], "question_idx": i,
                    "correct_idx": q["correct_idx"], "predicted_idx": -1, "correct": False,
                    "raw_response": f"ERROR: {str(exc)[:100]}", "tokens": 0,
                }
                out_f.write(json.dumps(result) + "\n")

            done += 1
            if done % 50 == 0:
                elapsed = time.time() - start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate / 60 if rate > 0 else 0
                print(f"  [{done}/{total}] rate={rate:.1f}/s ETA={eta:.0f}min")

    tasks = [process(q, i, model) for i, q in enumerate(questions) for model in MODELS]
    await asyncio.gather(*tasks)
    out_f.close()

    elapsed = time.time() - start
    print(f"\nDone: {total} evaluations in {elapsed/60:.1f}min")

    # Compute scores
    results = [json.loads(l) for l in open(output_file)]
    model_scores = {}
    for r in results:
        m = r["model"]
        if m not in model_scores:
            model_scores[m] = {"correct": 0, "total": 0}
        model_scores[m]["total"] += 1
        if r["correct"]:
            model_scores[m]["correct"] += 1

    print(f"\n{'Model':<20s} {'Score':>8s}")
    print("-" * 30)
    for m in sorted(model_scores, key=lambda m: model_scores[m]["correct"]/model_scores[m]["total"], reverse=True):
        s = model_scores[m]
        print(f"{m:<20s} {s['correct']/s['total']*100:7.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
