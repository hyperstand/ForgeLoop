"""ForgeLoop CLI: task-run, eval-run, compare (all offline-capable)."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .agent.engine import AgentEngine
from .agent.instructions import load_instructions
from .observe.ledger import Ledger, RunRecord
from .providers.factory import from_yaml
from .providers.mock_provider import MockProvider, assistant_text
from .tools.builtins import build_default_registry


def _provider(name: str, config: str = "examples/models.yaml"):
    if name == "mock":
        return MockProvider([assistant_text("mock run: no scripted steps")])
    try:
        return from_yaml(config, name)
    except (FileNotFoundError, KeyError):
        # Fall back to direct constructors when no config file exists.
        from .providers.anthropic import AnthropicProvider
        from .providers.openai_compat import OpenAICompatProvider

        if name == "openai_compat":
            return OpenAICompatProvider()
        if name == "anthropic":
            return AnthropicProvider()
        raise SystemExit(f"unknown provider: {name}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="forgeloop")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("task-run")
    t.add_argument("--task", required=True)
    t.add_argument("--provider", default="mock")
    t.add_argument("--config", default="examples/models.yaml")
    t.add_argument("--worktree", default=".")
    e = sub.add_parser("eval-run")
    e.add_argument("--suite", required=True)
    e.add_argument("--worktree", default=".")
    c = sub.add_parser("compare")
    c.add_argument("--baseline", required=True, help="baseline eval_report.json")
    c.add_argument("--candidate", required=True, help="candidate eval_report.json")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()

    if a.cmd == "task-run":
        prov = _provider(a.provider, a.config)
        eng = AgentEngine(prov, build_default_registry())
        t0 = time.time()
        res = eng.run(Path(a.task).read_text(), Path(a.worktree), load_instructions(Path(a.worktree)))
        Ledger().append(RunRecord(kind="agent_turn", provider=prov.name,
                                  model=getattr(prov, "model", prov.name), usage=res.usage,
                                  latency_s=round(time.time() - t0, 3)))
        print(json.dumps({"status": res.status, "summary": res.summary, "usage": res.usage}, indent=2))
    elif a.cmd == "eval-run":
        from .evals.runner import Runner

        t0 = time.time()
        rep = Runner().run(a.suite, Path(a.worktree))
        Ledger().append(RunRecord(kind="eval_run", provider="n/a", model="n/a",
                                  usage={}, latency_s=round(time.time() - t0, 3),
                                  meta={"suite": rep.suite, "passed": rep.passed, "failed": rep.failed}))
        print(rep.human())
        print(json.dumps(rep.to_dict(), indent=2))
    elif a.cmd == "compare":
        from .evals.runner import CaseResult, EvalReport

        def _load(p: str) -> EvalReport:
            d = json.loads(Path(p).read_text())
            rep = EvalReport(suite=d["suite"], dataset_version=d.get("dataset_version", "v1"))
            rep.results = [CaseResult(id=r["id"], passed=r["passed"], actual=r.get("actual"),
                                      expected=r.get("expected"), detail=r.get("detail", ""))
                           for r in d["results"]]
            return rep

        from .evals.runner import compare_reports

        print(json.dumps(compare_reports(_load(a.baseline), _load(a.candidate)), indent=2))
    elif a.cmd == "serve":
        from .web.server import serve

        if a.host not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit("refusing non-localhost bind without auth (see docs/security_model.md)")
        serve(a.host, a.port, Path(".").resolve()).serve_forever()


if __name__ == "__main__":
    main()
