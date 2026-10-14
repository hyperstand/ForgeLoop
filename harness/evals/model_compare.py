"""Model comparison: same suite, multiple providers/models, one table.

Every entry records provider, model, params, tool compatibility
(`capabilities()`), cost estimate, and the full report — so a model swap
never requires orchestrator changes and comparisons are auditable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..observe.ledger import Ledger, RunRecord
from .runner import EvalReport, compare_reports


@dataclass
class ModelEvalEntry:
    label: str
    provider: str
    model: str
    params: Dict[str, Any] = field(default_factory=dict)
    tool_compat: Dict[str, Any] = field(default_factory=dict)
    report: EvalReport | None = None
    latency_s: float = 0.0
    cost_usd: float = 0.0


def compare_models(entries: List[ModelEvalEntry], ledger: Ledger | None = None) -> Dict[str, Any]:
    rows = []
    for e in entries:
        assert e.report is not None, f"entry {e.label} has no report"
        rows.append({"label": e.label, "provider": e.provider, "model": e.model,
                     "params": e.params, "tool_compat": e.tool_compat,
                     "passed": e.report.passed, "failed": e.report.failed,
                     "latency_s": round(e.latency_s, 3), "cost_usd": e.cost_usd,
                     "dataset_version": e.report.dataset_version})
    base = rows[0]["label"] if rows else None
    pairwise = {}
    if len(entries) >= 2 and entries[0].report and entries[1].report:
        pairwise = compare_reports(entries[0].report, entries[1].report)
    result = {"entries": rows, "baseline": base, "pairwise": pairwise}
    if ledger is not None:
        ledger.append(RunRecord(
            kind="comparison", provider="+".join(r["provider"] for r in rows),
            model="+".join(r["model"] for r in rows),
            usage={}, latency_s=sum(r["latency_s"] for r in rows),
            cost_usd=sum(r["cost_usd"] for r in rows), meta=result))
    return result


def run_suite_for_providers(suite: str | Path, worktree: str | Path,
                            runners: List[Dict[str, Any]]) -> Dict[str, Any]:
    """runners: [{label, provider, model, params, tool_compat, run: Callable[[], EvalReport]}]."""
    from .runner import Runner  # noqa: F401  (kept for callers)
    entries = []
    for r in runners:
        t0 = time.time()
        report = r["run"]()
        entries.append(ModelEvalEntry(label=r["label"], provider=r.get("provider", "?"),
                                      model=r.get("model", "?"), params=r.get("params", {}),
                                      tool_compat=r.get("tool_compat", {}),
                                      report=report, latency_s=time.time() - t0,
                                      cost_usd=float(r.get("cost_usd", 0.0))))
    return compare_models(entries)


def to_markdown(comp: Dict[str, Any]) -> str:
    lines = ["# Model comparison"]
    for r in comp["entries"]:
        lines.append(f"- {r['label']} ({r['provider']}/{r['model']}): "
                     f"{r['passed']} passed, {r['failed']} failed, "
                     f"{r['latency_s']}s, ${r['cost_usd']}")
    if comp.get("pairwise"):
        p = comp["pairwise"]
        lines.append(f"Fixed vs baseline: {p['fixed']}; regressed: {p['regressed']}")
    return "\n".join(lines)
