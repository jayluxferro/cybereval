"""Competency profiling and visualization."""
from typing import List, Dict
from .evaluator import DimScore
from .framework import DIMENSIONS

class CompetencyProfiler:
    """Generate competency profiles for models."""
    
    def create_profile(self, dim_scores: List[DimScore]) -> Dict:
        return {s.dimension: {"score": s.score, "name": DIMENSIONS[s.dimension]} for s in dim_scores}
    
    def compute_gaps(self, dim_scores: List[DimScore], target: float = 0.7) -> Dict:
        gaps = {}
        for s in dim_scores:
            if s.score < target:
                gaps[s.dimension] = {"gap": target - s.score, "name": DIMENSIONS[s.dimension], "score": s.score}
        return dict(sorted(gaps.items(), key=lambda x: x[1]["gap"], reverse=True))
    
    def aggregate_score(self, dim_scores: List[DimScore]) -> float:
        if not dim_scores:
            return 0.0
        return sum(s.score for s in dim_scores) / len(dim_scores)
