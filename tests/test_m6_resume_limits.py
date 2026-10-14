"""M6 resume + resource-limit tests: checkpoints, wall-clock, token budget, output caps."""
import json
from pathlib import Path

from harness.agent.engine import AgentEngine, EngineConfig
from harness.providers.mock_provider import MockProvider, assistant_text, assistant_tool_calls
from harness.tasks.store import Task, TaskStore
from harness.tools.builtins import build_default_registry


def _wt(tmp_path: Path) -> Path:
    wt = tmp_path / "wt"
    wt.mkdir(exist_ok=True)
    (wt / "f.txt").write_text("v1")
    return wt


def test_checkpoint_resume_continues_without_repeating(tmp_path):
    wt = _wt(tmp_path)
    ckpt = tmp_path / "ckpt.json"
    # First run: one tool call, then stop via iteration budget.
    eng1 = AgentEngine(MockProvider([assistant_tool_calls(
        [{"id": "c1", "name": "read_file", "arguments": {"path": "f.txt"}}])]),
        build_default_registry(), EngineConfig(max_iterations=1))
    r1 = eng1.run("read it", wt, checkpoint_path=ckpt)
    assert r1.status == "budget_exceeded"  # never got a final message
    saved = json.loads(ckpt.read_text())
    assert len(saved["messages"]) == 4  # system, user, assistant-call, tool_result
    # Resume with the remaining script: edit + final answer.
    eng2 = AgentEngine(MockProvider([assistant_tool_calls(
        [{"id": "c2", "name": "edit_file", "arguments": {"path": "f.txt", "old_string": "v1", "new_string": "v2"}}]),
        assistant_text("done")]), build_default_registry(), EngineConfig(max_iterations=4))
    r2 = eng2.run("read it", wt, resume_from=ckpt)
    assert r2.status == "completed"
    assert (wt / "f.txt").read_text() == "v2"
    # Resume did not re-execute the first read: only 2 new provider calls consumed.
    assert eng2.provider.calls and len(eng2.provider.calls) == 2


def test_interrupted_task_resumes_with_history(tmp_path):
    store = TaskStore(tmp_path / "tasks")
    t = store.create(Task(id="T9", description="d"))
    store.transition(t, "INVESTIGATING")
    store.record_tool(t, "read_file", {"path": "f.txt"}, {"content": "v1"})
    back = store.resume("T9")
    assert back.state == "INVESTIGATING" and len(back.tool_activity) == 1
    store.transition(back, "PLANNED")  # lifecycle continues from restored state


def test_wall_clock_budget_stops(tmp_path):
    eng = AgentEngine(MockProvider([assistant_text("late")]), build_default_registry(),
                      EngineConfig(wall_clock_s=0.0))
    assert eng.run("t", _wt(tmp_path)).status == "budget_exceeded"


def test_token_budget_stops(tmp_path):
    eng = AgentEngine(MockProvider([assistant_text("late")]), build_default_registry(),
                      EngineConfig(token_budget=1))
    assert eng.run("t", _wt(tmp_path)).status == "budget_exceeded"


def test_output_cap_truncates_final_text(tmp_path):
    eng = AgentEngine(MockProvider([assistant_text("x" * 5000)]), build_default_registry(),
                      EngineConfig(max_output_bytes=100))
    res = eng.run("t", _wt(tmp_path))
    assert res.status == "completed" and len(res.summary) <= 200
