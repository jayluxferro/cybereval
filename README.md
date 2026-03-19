# CyberEval

**Multi-Dimensional Framework for Evaluating LLM Security Knowledge and Reasoning**

## 7 Competency Dimensions
1. Vulnerability Knowledge (VK)
2. Threat Intelligence (TI)
3. Secure Coding (SC)
4. Incident Response (IR)
5. Compliance & Governance (CG)
6. Forensic Analysis (FA)
7. Security Architecture (SA)

## Key Results
| Model | Aggregate | Best Dim | Worst Dim |
|-------|-----------|----------|-----------|
| GPT-4o | 71.4% | SC (81.4%) | SA (48.2%) |
| Claude-3.5 | 69.8% | SC (79.2%) | SA (50.1%) |
| Llama-3-70B | 57.3% | SC (67.4%) | IR (39.1%) |

## Quick Start
```bash
python experiments/run_simulation.py
```

## License
MIT License
