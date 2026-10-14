"""Candidate findings grouped from review records. Explicit approval gate."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


class FindingError(Exception):
    pass


@dataclass
class Finding:
    id: str
    title: str
    subsystem: str
    trace_refs: List[str]
    repro: List[str]
    expected: str
    actual: str
    hypothesis: str
    frequency: int = 1
    impact: str = "medium"
    confidence: float = 0.5
    counterexamples: List[str] = field(default_factory=list)
    eval_criteria: str = ""
    status: str = "draft"  # draft | approved | rejected

    def approve(self) -> "Finding":
        if len(self.trace_refs) < 1:
            raise FindingError("need at least one trace reference")
        if self.confidence < 0.5:
            raise FindingError("confidence too low to approve")
        if not self.eval_criteria:
            raise FindingError("eval_criteria required before approval")
        self.status = "approved"
        return self

    def reject(self, reason: str = "") -> "Finding":
        self.status = "rejected"
        return self


def group_reviews(finding_id: str, title: str, subsystem: str, trace_ids: List[str], **kw) -> Finding:
    """One unverified correction must NOT auto-approve: status stays draft until approve()."""
    return Finding(id=finding_id, title=title, subsystem=subsystem, trace_refs=list(trace_ids), **kw)
