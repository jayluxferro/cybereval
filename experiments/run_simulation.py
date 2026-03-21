#!/usr/bin/env python3
"""Compatibility entry point for CyberEval experiments.

The paper and repo convention expect `experiments/run_simulation.py` to be the
main executable. The legacy version hard-coded figures and stale summary JSON.
This wrapper now delegates to the reproducible evaluation pipeline in
`run_real_evaluation.py`, which generates the paper figures plus aligned result
artifacts (`real_results.json`, `experimental_results.json`, question bank, and
response traces).
"""

from run_real_evaluation import run_evaluation


if __name__ == "__main__":
    run_evaluation()
