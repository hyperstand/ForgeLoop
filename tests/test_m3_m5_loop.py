"""M3-M5 tests: traces, feedback gates, eval integrity/regression, evidence protection."""
import json
from pathlib import Path

import pytest
import yaml

from harness.evals.runner import EvalIntegrityError, Runner, compare_reports
from harness.feedback.evalgen import finding_to_eval_case
from harness.feedback.findings import FindingError, group_reviews
from harness.feedback.reviews import classify
from harness.traces.schema import Trace, TraceStore

DEMO = Path("demo/fair_rental_days")


def test_trace_provenance_roundtrip(tmp_path):
    st = TraceStore(tmp_path)
    t = Trace(id="t1", task_id="k", provider="mock", model="mock-1", prediction={"a": 1},
              tool_calls=[{"tool": "read_file"}], usage={"tokens_in": 1})
    st.append(t)
    back = st.get("t1")
    assert back.prediction == {"a": 1} and back.tool_calls[0]["tool"] == "read_file" and back.version == "v1"


def test_trace_redacts_secrets(tmp_path):
    st = TraceStore(tmp_path)
    st.append(Trace(id="t2", task_id="k", intermediates=[{"api_key": "shhh-123"}]))
    blob = (tmp_path / "t2.json").read_text()
    assert "shhh-123" not in blob


def test_single_unverified_correction_cannot_become_eval():
    f = group_reviews("FIND-X-1", "t", "s", ["trace-1"], repro=["r"], expected="e",
                      actual="a", hypothesis="h", eval_criteria="c")
    assert f.status == "draft"
    with pytest.raises(FindingError):
        finding_to_eval_case(f, "m", "fn", "fx", "ex")  # not approved
    f.approve()  # explicit approval required before eval generation
    assert f.status == "approved"
    case = finding_to_eval_case(f, "m", "fn", "fx", "ex")
    assert case.id == "find-x-1-001"


def test_low_confidence_finding_rejected():
    f = group_reviews("FIND-X-2", "t", "s", ["trace-1"], repro=["r"], expected="e",
                      actual="a", hypothesis="h", confidence=0.2, eval_criteria="c")
    with pytest.raises(FindingError):
        f.approve()


def test_workflow_noise_not_actionable():
    r = classify({"a": 1}, {"a": 1}, ["ev"], "workflow_noise", 0.8)
    assert not r.actionable


def test_eval_baseline_fails_candidate_passes_and_regression_detects(tmp_path):
    r = Runner()
    base = r.run(DEMO / "suites" / "fair-rental-days.yaml", DEMO / "repo")
    assert base.failed == 1
    # candidate copy with the one-line fix
    cand = tmp_path / "repo" / "app"
    cand.mkdir(parents=True)
    src = (DEMO / "repo" / "app" / "mapper.py").read_text()
    (cand / "mapper.py").write_text(src.replace('"fair_rental_days": 0,', '"fair_rental_days": int(doc.get("fair_rental_days", 0)),'))
    fixed = r.run(DEMO / "suites" / "fair-rental-days.yaml", tmp_path / "repo")
    assert fixed.failed == 0
    cmp = compare_reports(base, fixed)
    assert cmp["fixed"] == ["fair-rental-days-001"] and cmp["regressed"] == []
    # seeded regression: break other_expenses in candidate -> regression suite catches it
    (cand / "mapper.py").write_text(src.replace('"other_expenses": doc.get("other_expenses", 0),', '"other_expenses": 999,'))
    reg = r.run(DEMO / "suites" / "rental-income-regression.yaml", tmp_path / "repo")
    assert reg.failed >= 1


def test_eval_results_reproducible():
    r = Runner()
    a = r.run(DEMO / "suites" / "fair-rental-days.yaml", DEMO / "repo")
    b = r.run(DEMO / "suites" / "fair-rental-days.yaml", DEMO / "repo")
    assert a.to_dict()["results"] == b.to_dict()["results"]


def test_protected_expectations_mutation_fails_run(tmp_path):
    import shutil

    suite_src = DEMO / "suites" / "fair-rental-days.yaml"
    work = tmp_path / "w"
    (work / "suites").mkdir(parents=True)
    shutil.copy(suite_src, work / "suites" / "s.yaml")
    shutil.copytree(DEMO / "fixtures", work / "fixtures")
    shutil.copytree(DEMO / "expected", work / "expected")
    spec = yaml.safe_load((work / "suites" / "s.yaml").read_text())
    # point suite at the copies, then mutate expected mid-run via a hostile grader module
    (work / "repo" / "app").mkdir(parents=True)
    (work / "repo" / "app" / "mapper.py").write_text(
        "import json, pathlib\ndef map_rental(doc):\n"
        "    pathlib.Path(r'" + str((work / "expected" / "rental_001.json")).replace("\\", "/") + "').write_text(json.dumps({'fair_rental_days': 0, 'other_expenses': 120}))\n"
        "    return {'fair_rental_days': 0, 'other_expenses': 120}\n")
    spec["cases"][0]["fixture"] = "../fixtures/rental_001.json"
    spec["cases"][0]["expected"] = "../expected/rental_001.json"
    (work / "suites" / "s.yaml").write_text(yaml.safe_dump(spec))
    with pytest.raises(EvalIntegrityError):
        Runner().run(work / "suites" / "s.yaml", work / "repo")


def test_evidence_lives_outside_writable_repo():
    assert (Path("candidates") / "FIND-RENTAL-0042" / "evidence").parts[-1] == "evidence"
    # demo baseline repo must not contain evidence dir (separation by layout)
    assert not (DEMO / "repo" / "evidence").exists()
