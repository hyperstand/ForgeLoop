"""End-to-end feedback-to-fix demo (offline, mock provider).

Steps: trace -> correction -> classification -> finding -> approval -> eval (baseline FAIL)
-> bounded task -> agent fix -> targeted PASS -> regression PASS -> patch + report.
Run: python demo/run_demo.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # demo/
DEMO = ROOT / "fair_rental_days"
REPO_ROOT = ROOT.parent
CAND = REPO_ROOT / "candidates" / "FIND-RENTAL-0042"

sys.path.insert(0, str(REPO_ROOT))

from harness.agent.engine import AgentEngine, EngineConfig  # noqa: E402
from harness.evals.runner import Runner, compare_reports  # noqa: E402
from harness.feedback.evalgen import finding_to_eval_case  # noqa: E402
from harness.feedback.findings import group_reviews  # noqa: E402
from harness.feedback.reviews import classify  # noqa: E402
from harness.providers.mock_provider import MockProvider, assistant_text, assistant_tool_calls  # noqa: E402
from harness.tools.builtins import build_default_registry  # noqa: E402
from harness.traces.schema import Trace, TraceStore  # noqa: E402

FIX_OLD = '"fair_rental_days": 0,'
FIX_NEW = '"fair_rental_days": int(doc.get("fair_rental_days", 0)),'


def main() -> int:
    runner = Runner()
    # 1-2. Baseline: buggy mapper must FAIL the targeted eval.
    baseline = runner.run(DEMO / "suites" / "fair-rental-days.yaml", DEMO / "repo")
    print(baseline.human())
    assert baseline.failed == 1, "demo precondition: baseline must fail"

    # 3. Trace + verified correction.
    store = TraceStore(REPO_ROOT / ".harness" / "traces")
    trace = Trace(id="trace-rental-001", task_id="demo", provider="mock", model="mock-1",
                  prediction={"fair_rental_days": 0}, correction={"fair_rental_days": 5},
                  outcome="corrected", context_refs=["fixtures/rental_001.json"])
    store.append(trace)
    review = classify(trace.prediction, trace.correction, ["fixtures/rental_001.json"],
                      "mapping_error", 0.9)
    review.trace_id = trace.id
    print(f"classified: {review.category} actionable={review.actionable}")

    # 4-5. Finding + explicit approval.
    finding = group_reviews("FIND-RENTAL-0042", "fair_rental_days dropped by mapper",
                            "rental-income", [trace.id],
                            repro=["run fair-rental-days suite against baseline"],
                            expected="fair_rental_days == 5", actual="fair_rental_days == 0",
                            hypothesis="mapper hardcodes 0 instead of reading the field",
                            frequency=3, impact="high", confidence=0.9,
                            eval_criteria="fair-rental-days-001 passes; regression clean")
    finding.approve()
    case = finding_to_eval_case(finding, "app.mapper", "map_rental", "../fixtures/rental_001.json",
                                "../expected/rental_001.json", keys=["fair_rental_days", "other_expenses"],
                                category="mapping_error")
    print(f"finding {finding.id} approved -> eval case {case.id}")

    # 6. Bounded task env (repo/ writable; evidence/ + eval copies read-only by convention).
    for sub in ("repo", "evidence", "evals", "artifacts"):
        (CAND / sub).mkdir(parents=True, exist_ok=True)
    shutil.copytree(DEMO / "repo", CAND / "repo", dirs_exist_ok=True)
    shutil.copy(DEMO / "fixtures" / "rental_001.json", CAND / "evidence" / "rental_001.json")
    shutil.copy(DEMO / "suites" / "fair-rental-days.yaml", CAND / "evals" / "fair-rental-days.yaml")
    (CAND / "task.yaml").write_text(
        f"finding: {finding.id}\nallow_edit: ['app/mapper.py']\nforbid: ['evidence/', 'evals/expected']\n"
        f"acceptance: ['fair-rental-days-001 passes', 'regression clean', 'human APPROVED']\n")
    (CAND / "EXEC_PLAN.md").write_text("# Plan\n1. Read app/mapper.py\n2. Fix fair_rental_days mapping\n3. Run evals\n")

    # 7. Coding agent (mock, scripted) implements the candidate fix inside candidate repo only.
    script = [
        assistant_tool_calls([{"id": "c1", "name": "read_file", "arguments": {"path": "app/mapper.py"}}]),
        assistant_tool_calls([{"id": "c2", "name": "edit_file", "arguments": {
            "path": "app/mapper.py", "old_string": FIX_OLD, "new_string": FIX_NEW}}]),
        assistant_text("fix applied: read fair_rental_days from input"),
    ]
    eng = AgentEngine(MockProvider(script), build_default_registry(), EngineConfig(max_iterations=6))
    res = eng.run("Fix fair_rental_days mapping per task.yaml", CAND / "repo")
    assert res.status == "completed", res.summary

    # 8-9. Targeted + regression on the CANDIDATE (not by editing expectations).
    targeted = runner.run(DEMO / "suites" / "fair-rental-days.yaml", CAND / "repo")
    regression = runner.run(DEMO / "suites" / "rental-income-regression.yaml", CAND / "repo")
    print(targeted.human())
    print(regression.human())
    assert targeted.failed == 0, "targeted eval must pass after fix"
    assert regression.failed == 0, "regression must be clean"
    cmp_target = compare_reports(baseline, targeted)
    assert cmp_target["fixed"] == ["fair-rental-days-001"], cmp_target

    # 10. Patch + review report (approval stays manual).
    diff = subprocess.run(["git", "diff", "--no-index", str(DEMO / "repo" / "app" / "mapper.py"),
                           str(CAND / "repo" / "app" / "mapper.py")],
                          capture_output=True, text=True).stdout
    (CAND / "artifacts").mkdir(exist_ok=True)
    (CAND / "artifacts" / "eval_report.json").write_text(
        json.dumps({"targeted": targeted.to_dict(), "regression": regression.to_dict(), "diff": cmp_target}, indent=2))
    (CAND / "RESULTS.md").write_text(
        f"# RESULTS — {finding.id}\n\n## Baseline\n{baseline.human()}\n\n## Candidate\n{targeted.human()}\n"
        f"\n{regression.human()}\n\n## Diff\n```diff\n{diff}\n```\n\n## Approval\nStatus: REVIEW_REQUIRED "
        f"(human must approve; model claim is not proof)\n")
    print(f"demo OK: {CAND / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
