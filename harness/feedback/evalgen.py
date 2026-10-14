"""Finding -> versioned evaluation case (never from a single unverified correction)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .findings import Finding, FindingError


@dataclass
class EvalCase:
    id: str
    module: str
    function: str
    fixture: str
    expected: str
    method: str = "exact"  # exact | tolerance
    keys: List[str] | None = None
    tol: float = 0.0
    category: str = ""
    dataset_version: str = "v1"


def finding_to_eval_case(finding: Finding, module: str, function: str, fixture: str,
                         expected: str, method: str = "exact", keys: List[str] | None = None,
                         tol: float = 0.0, category: str = "", dataset_version: str = "v1") -> EvalCase:
    if finding.status != "approved":
        raise FindingError("finding must be approved before generating an eval case")
    return EvalCase(id=finding.id.lower() + "-001", module=module, function=function, fixture=fixture,
                    expected=expected, method=method, keys=keys, tol=tol, category=category or "mapping_error",
                    dataset_version=dataset_version)


def case_to_dict(c: EvalCase) -> Dict[str, Any]:
    return asdict(c)
