"""M6 observability tests: ledger costs, model comparison, CLI compare."""
import json
import shutil
from pathlib import Path

from harness.evals.model_compare import ModelEvalEntry, compare_models, run_suite_for_providers, to_markdown
from harness.evals.runner import Runner
from harness.observe.ledger import Ledger, RunRecord

DEMO = Path("demo/fair_rental_days")


def test_ledger_costs_and_summary(tmp_path):
    lg = Ledger(tmp_path / "ledger.jsonl")
    lg.append(RunRecord(kind="agent_turn", provider="mock", model="mock-1",
                        usage={"tokens_in": 1000, "tokens_out": 500}))
    lg.append(RunRecord(kind="eval_run", provider="openai_compat", model="gpt-4o-mini",
                        usage={"tokens_in": 1000, "tokens_out": 1000}))
    s = lg.summary()
    assert s["runs"] == 2 and s["total_cost_usd"] > 0
    assert "mock" in s["by_provider"]


def test_model_comparison_same_suite_two_worktrees(tmp_path):
    r = Runner()
    baseline = r.run(DEMO / "suites" / "fair-rental-days.yaml", DEMO / "repo")
    cand = tmp_path / "repo" / "app"
    cand.mkdir(parents=True)
    src = (DEMO / "repo" / "app" / "mapper.py").read_text()
    (cand / "mapper.py").write_text(src.replace('"fair_rental_days": 0,',
                                                '"fair_rental_days": int(doc.get("fair_rental_days", 0)),'))
    fixed = r.run(DEMO / "suites" / "fair-rental-days.yaml", tmp_path / "repo")
    comp = run_suite_for_providers(
        DEMO / "suites" / "fair-rental-days.yaml", tmp_path / "repo",
        [{"label": "baseline-mock", "provider": "mock", "model": "mock-1",
          "tool_compat": {"tool_calling": True}, "run": lambda: baseline},
         {"label": "candidate-mock", "provider": "mock", "model": "mock-1",
          "tool_compat": {"tool_calling": True}, "run": lambda: fixed}])
    assert comp["pairwise"]["fixed"] == ["fair-rental-days-001"]
    md = to_markdown(comp)
    assert "baseline-mock" in md and "candidate-mock" in md


def test_compare_models_records_ledger(tmp_path):
    r = Runner()
    rep = r.run(DEMO / "suites" / "rental-income-regression.yaml", DEMO / "repo")
    lg = Ledger(tmp_path / "l.jsonl")
    comp = compare_models([ModelEvalEntry(label="a", provider="mock", model="mock-1", report=rep)], ledger=lg)
    assert lg.summary()["runs"] == 1
    # Baseline mapper is buggy: rental_003 (fair_rental_days=12) fails, rental_002 passes.
    assert (comp["entries"][0]["passed"], comp["entries"][0]["failed"]) == (1, 1)
