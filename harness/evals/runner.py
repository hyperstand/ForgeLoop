"""Repeatable eval runner: fixture integrity, targeted + regression, baseline diff."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


class EvalIntegrityError(Exception):
    pass


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@dataclass
class CaseResult:
    id: str
    passed: bool
    actual: Any = None
    expected: Any = None
    detail: str = ""
    latency_s: float = 0.0


@dataclass
class EvalReport:
    suite: str
    dataset_version: str
    results: List[CaseResult] = field(default_factory=list)
    elapsed_s: float = 0.0
    code_version: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def to_dict(self) -> Dict[str, Any]:
        return {"suite": self.suite, "dataset_version": self.dataset_version, "passed": self.passed,
                "failed": self.failed, "elapsed_s": round(self.elapsed_s, 3), "code_version": self.code_version,
                "results": [{"id": r.id, "passed": r.passed, "actual": r.actual, "expected": r.expected,
                             "detail": r.detail} for r in self.results]}

    def human(self) -> str:
        lines = [f"# Eval report: {self.suite} — {self.passed} passed, {self.failed} failed"]
        for r in self.results:
            lines.append(f"- [{'PASS' if r.passed else 'FAIL'}] {r.id}: {r.detail}")
        return "\n".join(lines)


def _load_fn(worktree: Path, module: str, function: str):
    mod_path = worktree / (module.replace(".", "/") + ".py")
    if not mod_path.is_file():
        raise EvalIntegrityError(f"module not found: {module}")
    spec = importlib.util.spec_from_file_location(f"_eval_{module.replace('.', '_')}", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, function, None)
    if not callable(fn):
        raise EvalIntegrityError(f"function not found: {module}.{function}")
    return fn


def compare_reports(baseline: EvalReport, candidate: EvalReport) -> Dict[str, Any]:
    b = {r.id: r.passed for r in baseline.results}
    c = {r.id: r.passed for r in candidate.results}
    fixed = sorted(i for i in c if c[i] and not b.get(i, True))
    regressed = sorted(i for i in c if not c[i] and b.get(i, False))
    return {"fixed": fixed, "regressed": regressed,
            "baseline": {"passed": baseline.passed, "failed": baseline.failed},
            "candidate": {"passed": candidate.passed, "failed": candidate.failed}}


class Runner:
    def run(self, suite: str | Path, worktree: str | Path) -> EvalReport:
        t0 = time.time()
        suite_p = Path(suite)
        wt = Path(worktree)
        spec = yaml.safe_load(suite_p.read_text())
        dv = str(spec.get("dataset_version", "v1"))
        base = suite_p.parent
        # Snapshot integrity BEFORE running (agent must not mutate expectations mid-run).
        snaps: Dict[str, str] = {}
        for c in spec.get("cases", []):
            for key in ("fixture", "expected"):
                p = (base / c[key]).resolve() if not Path(c[key]).is_absolute() else Path(c[key])
                if not p.is_file():
                    raise EvalIntegrityError(f"missing {key}: {c[key]}")
                snaps[str(p)] = sha256_file(p)
        results: List[CaseResult] = []
        for c in spec.get("cases", []):
            t1 = time.time()
            fx = json.loads(((base / c["fixture"])).read_text())
            ex = json.loads(((base / c["expected"])).read_text())
            fn = _load_fn(wt, c["module"], c["function"])
            try:
                actual_full = fn(fx)
            except Exception as e:
                results.append(CaseResult(c["id"], False, None, ex, f"ERROR {type(e).__name__}: {e}", time.time() - t1))
                continue
            keys = c.get("keys")
            actual = {k: actual_full.get(k) for k in keys} if keys else actual_full
            expected = {k: ex.get(k) for k in keys} if keys else ex
            method = c.get("method", "exact")
            if method == "tolerance":
                tol = float(c.get("tol", 0.0))
                ok = all(abs(float(actual.get(k, 0)) - float(expected.get(k, 0))) <= tol for k in expected)
            else:
                ok = actual == expected
            results.append(CaseResult(c["id"], ok, actual, expected,
                                      "match" if ok else f"actual={actual} expected={expected}", time.time() - t1))
        # Re-verify integrity AFTER running.
        for pstr, sha in snaps.items():
            if sha256_file(Path(pstr)) != sha:
                raise EvalIntegrityError(f"eval fixture mutated during run: {pstr}")
        return EvalReport(suite=suite_p.name, dataset_version=dv, results=results,
                          elapsed_s=time.time() - t0, code_version=self._code_version(wt))

    @staticmethod
    def _code_version(wt: Path) -> str:
        import subprocess

        try:
            r = subprocess.run(["git", "diff", "--stat"], cwd=wt, capture_output=True, text=True, timeout=15)
            return (r.stdout or "").strip()[:500]
        except OSError:
            return ""
