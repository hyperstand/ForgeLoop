"""Minimal CLI: task-run and eval-run (offline-capable)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent.engine import AgentEngine
from .agent.instructions import load_instructions
from .providers.mock_provider import MockProvider, assistant_text
from .providers.openai_compat import OpenAICompatProvider
from .tools.builtins import build_default_registry


def _provider(name: str):
    if name == "mock":
        return MockProvider([assistant_text("mock run: no scripted steps")])
    if name == "openai_compat":
        return OpenAICompatProvider()
    raise SystemExit(f"unknown provider: {name}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("task-run")
    t.add_argument("--task", required=True)
    t.add_argument("--provider", default="mock")
    t.add_argument("--worktree", default=".")
    e = sub.add_parser("eval-run")
    e.add_argument("--suite", required=True)
    e.add_argument("--worktree", default=".")
    a = ap.parse_args()

    if a.cmd == "task-run":
        eng = AgentEngine(_provider(a.provider), build_default_registry())
        res = eng.run(Path(a.task).read_text(), Path(a.worktree), load_instructions(Path(a.worktree)))
        print(json.dumps({"status": res.status, "summary": res.summary, "usage": res.usage}, indent=2))
    elif a.cmd == "eval-run":
        from .evals.runner import Runner

        rep = Runner().run(a.suite, Path(a.worktree))
        print(rep.human())
        print(json.dumps(rep.to_dict(), indent=2))


if __name__ == "__main__":
    main()
