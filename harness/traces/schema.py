"""Versioned trace schema (v1). Append-only; secrets redacted."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..security.policy import redact

TRACE_VERSION = "v1"

CATEGORIES = ("missing_capability", "incorrect_retrieval", "wrong_tool", "schema_mismatch",
              "mapping_error", "business_rule", "unsupported_reasoning", "grader_defect",
              "workflow_noise", "insufficient_evidence")


@dataclass
class Trace:
    id: str
    task_id: str
    ts: str = ""
    provider: str = ""
    model: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    context_refs: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    retrieved_evidence: List[str] = field(default_factory=list)
    intermediates: List[Any] = field(default_factory=list)
    prediction: Any = None
    correction: Any = None
    outcome: str = ""
    errors: List[str] = field(default_factory=list)
    usage: Dict[str, Any] = field(default_factory=dict)
    code_versions: Dict[str, str] = field(default_factory=dict)
    version: str = TRACE_VERSION

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()


class TraceStore:
    def __init__(self, root: str | Path = ".harness/traces"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, trace: Trace) -> Path:
        blob = json.loads(redact(json.dumps(asdict(trace))))
        p = self.root / f"{trace.id}.json"
        p.write_text(json.dumps(blob, indent=2))
        return p

    def get(self, trace_id: str) -> Trace:
        d = json.loads((self.root / f"{trace_id}.json").read_text())
        return Trace(**d)
