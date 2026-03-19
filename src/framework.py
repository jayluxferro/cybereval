"""CyberEval evaluation framework."""
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional

DIMENSIONS = {
    "VK": "Vulnerability Knowledge",
    "TI": "Threat Intelligence",
    "SC": "Secure Coding",
    "IR": "Incident Response",
    "CG": "Compliance & Governance",
    "FA": "Forensic Analysis",
    "SA": "Security Architecture",
}

@dataclass
class EvalItem:
    item_id: str
    dimension: str
    format: str  # "mcq", "code_analysis", "scenario", "open_ended"
    difficulty: int
    question: str
    answer: str
    options: List[str] = field(default_factory=list)

class CyberEvalFramework:
    """Generate and manage evaluation items."""
    
    ITEM_COUNTS = {"VK": 721, "TI": 634, "SC": 687, "IR": 598, "CG": 512, "FA": 543, "SA": 536}
    
    def generate_items(self, n_per_dim: int = 100) -> List[EvalItem]:
        items = []
        for dim_code, dim_name in DIMENSIONS.items():
            for i in range(n_per_dim):
                fmt = random.choice(["mcq", "mcq", "scenario", "code_analysis"])
                items.append(EvalItem(
                    item_id=f"{dim_code}-{i+1:04d}",
                    dimension=dim_code,
                    format=fmt,
                    difficulty=random.randint(1, 10),
                    question=f"[{dim_name}] Sample question {i+1}",
                    answer=f"Answer for {dim_code}-{i+1}",
                    options=[f"Option {j}" for j in range(4)] if fmt == "mcq" else [],
                ))
        return items
