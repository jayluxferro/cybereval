"""Balance correct-answer positions across the full 250-item CyberEval bank.

The original 210 items all carried the correct answer at option A (position 0) —
a degenerate answer key that would credit an "always A" model with a perfect
score. This script reorders the four options of every item so that
correct-answer positions are balanced across the bank (62/62/63/63 for 250 items)
using a deterministic seeded search. Item content, ids, dimensions, and
difficulty annotations are unchanged; only option order changes.

Usage: python experiments/balance_bank.py
Writes: experiments/results/question_bank.json (250 items, balanced positions)
Also writes: experiments/results/bank_balance_provenance.json (seed + counts)
"""

import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / "experiments/results/question_bank.json"
PROV_PATH = ROOT / "experiments/results/bank_balance_provenance.json"


def balance(items, start_seed=7, max_attempts=1000):
    """Deterministically reorder options of every item until positions are balanced.

    Returns (seed_used, balanced_items). Fails loudly if no seed in range works.
    """
    n = len(items)
    target = n / 4  # 62.5 for 250 items -> counts must be within 1 of each other
    for seed in range(start_seed, start_seed + max_attempts):
        rng = random.Random(seed)
        out = []
        for it in items:
            choices = it["choices"][:]
            rng.shuffle(choices)
            new_correct = choices.index(it["choices"][it["correct"]])
            out.append({**it, "choices": choices, "correct": new_correct})
        counts = Counter(o["correct"] for o in out)
        if set(counts) == {0, 1, 2, 3} and max(counts.values()) - min(counts.values()) <= 1:
            # Sanity: every item still carries its original correct answer text.
            for it, o in zip(items, out):
                assert o["choices"][o["correct"]] == it["choices"][it["correct"]]
            return seed, out
    raise RuntimeError(f"no balanced shuffle found in {max_attempts} seeds")


def main():
    bank = json.loads(BANK_PATH.read_text())
    if len(bank) != 250:
        raise RuntimeError(f"expected 250 items, found {len(bank)}")

    seed, balanced = balance(bank)
    counts = dict(Counter(b["correct"] for b in balanced))
    print(f"seed={seed} balanced counts={counts} (n={len(balanced)})")

    json.dump(balanced, BANK_PATH.open("w"), indent=2)
    json.dump(
        {
            "note": ("Correct-answer positions balanced with deterministic seeded shuffle; "
                     "original 210 items all had correct answer at position 0 (option A)."),
            "seed": seed,
            "n_items": len(balanced),
            "position_counts": counts,
        },
        PROV_PATH.open("w"),
        indent=2,
    )
    print(f"wrote {BANK_PATH}")
    print(f"wrote {PROV_PATH}")


if __name__ == "__main__":
    main()
