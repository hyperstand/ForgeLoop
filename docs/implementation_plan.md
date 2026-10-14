# ForgeLoop — Implementation Plan — milestones and acceptance

## M1 Research + architecture — DONE when docs/ has 8 files + AGENTS.md + git init
- Acceptance: `architecture_research.md` cites sources with verified/inferred split; audit states empty start.

## M2 Minimal harness (this build)
- Files: `harness/providers/*, agent/engine.py, tools/*, workspace/manager.py, tasks/*`.
- Acceptance: mocked-model task lists/reads/edits a file in an isolated worktree, runs allowlisted
  `pytest`, returns `AgentResult`; `pytest -q` green offline.

## M3 Evaluation infra
- Files: `harness/traces/*, harness/evals/*`, `evals/suites/*.yaml` fixtures.
- Acceptance: targeted suite + regression suite run; baseline-vs-candidate diff detects a seeded regression.

## M4 Feedback → task
- Files: `harness/feedback/*`, approval gate in tasks.
- Acceptance: correction → review → finding → approved eval case → `candidates/<id>/task.yaml`;
  single unverified correction does NOT create a task (test asserts).

## M5 Coding-agent integration
- Files: `demo/fair_rental_days/*`, `demo/run_demo.py`, candidate patch flow.
- Acceptance: baseline eval fails, candidate fix passes targeted + regression, `RESULTS.md` + patch +
  engineering report generated; eval expectations immutable during run (test asserts SHA).

## M6 Multi-model + hardening (deferred)
- Second live adapter (Anthropic or Ollama-local), model comparison log, resume tests, security tests,
  observability. Acceptance: live tests skip cleanly without creds; documented in limitations.md.

## Runnable-state rule
Every milestone ends with `pytest -q` green and `python demo/run_demo.py` (from M5) reproducible.
