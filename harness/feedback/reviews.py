"""Review records: prediction vs verified correction + failure classification."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from ..traces.schema import CATEGORIES

NON_ACTIONABLE = {"workflow_noise", "insufficient_evidence"}


@dataclass
class ReviewRecord:
    trace_id: str
    predicted: Any
    corrected: Any
    evidence: List[str]
    category: str
    actionable: bool
    confidence: float
    reviewer: str = "human"
    status: str = "reviewed"  # reviewed | ambiguous

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category: {self.category}")
        if self.category in NON_ACTIONABLE and self.actionable:
            raise ValueError(f"{self.category} must not be marked actionable without further evidence")


def classify(predicted: Any, corrected: Any, evidence: List[str], category: str,
             confidence: float, reviewer: str = "human") -> ReviewRecord:
    actionable = category not in NON_ACTIONABLE
    status = "reviewed" if confidence >= 0.5 else "ambiguous"
    return ReviewRecord(trace_id="", predicted=predicted, corrected=corrected, evidence=evidence,
                        category=category, actionable=actionable, confidence=confidence,
                        reviewer=reviewer, status=status)
