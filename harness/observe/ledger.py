"""Run ledger: every provider call and eval run recorded with cost + latency."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# USD per 1k tokens. Overrides via Ledger(rates={...}). Mock is free by definition.
DEFAULT_RATES = {
    "mock-1": (0.0, 0.0),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-sonnet-4-5": (0.003, 0.015),
}


@dataclass
class RunRecord:
    kind: str  # agent_turn | eval_run | comparison
    provider: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    latency_s: float = 0.0
    cost_usd: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)
    ts: str = ""


class Ledger:
    def __init__(self, path: str | Path = ".harness/ledger.jsonl", rates: Dict[str, Any] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rates = rates or DEFAULT_RATES

    @staticmethod
    def estimate_cost(model: str, tokens_in: int, tokens_out: int, rates: Dict[str, Any]) -> float:
        rin, rout = rates.get(model, (0.0, 0.0))
        return tokens_in / 1000 * rin + tokens_out / 1000 * rout

    def append(self, rec: RunRecord) -> RunRecord:
        if not rec.ts:
            rec.ts = datetime.now(timezone.utc).isoformat()
        if not rec.cost_usd and rec.usage:
            rec.cost_usd = round(self.estimate_cost(rec.model, int(rec.usage.get("tokens_in", 0)),
                                                    int(rec.usage.get("tokens_out", 0)), self.rates), 6)
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")
        return rec

    def read_all(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def summary(self) -> Dict[str, Any]:
        rows = self.read_all()
        return {"runs": len(rows),
                "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in rows), 6),
                "total_latency_s": round(sum(r.get("latency_s", 0) for r in rows), 3),
                "by_provider": sorted({r.get("provider", "?") for r in rows})}
