"""Persisted finding store (JSON files). Approval stays explicit via Finding.approve()."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from .findings import Finding


class FindingStore:
    def __init__(self, root: str | Path = ".harness/findings"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, finding: Finding) -> Path:
        p = self.root / f"{finding.id}.json"
        p.write_text(json.dumps(asdict(finding), indent=2))
        return p

    def load(self, finding_id: str) -> Finding:
        return Finding(**json.loads((self.root / f"{finding_id}.json").read_text()))

    def list(self) -> List[Finding]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            try:
                out.append(Finding(**json.loads(p.read_text())))
            except (OSError, TypeError, KeyError):
                continue
        return out

    def approve(self, finding_id: str) -> Finding:
        f = self.load(finding_id)
        f.approve()  # same validation gate as the library: criteria + confidence + trace ref
        self.save(f)
        return f

    def to_dict(self) -> Dict[str, list]:
        return {"findings": [asdict(f) for f in self.list()]}
