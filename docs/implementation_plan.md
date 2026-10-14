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

## M6 Multi-model + hardening — SHIPPED (live runs pending creds)
- Second live adapter (`anthropic.py`, native Messages API) + config-driven factory
  (`providers/factory.py`; `examples/models.yaml` covers mock/openai_compat/anthropic).
- Model comparison (`evals/model_compare.py`: same suite, provider/model/params/tool-compat/cost table).
- Resumability: engine checkpoints (`checkpoint_path`/`resume_from`) + `TaskStore.resume` tests.
- Resource limits: iteration/wall-clock/token/tool-call/output-cap tests.
- Security tests: jail escapes (incl. symlink), denylist backstop, exec gating, redaction, injection-as-data.
- Observability: run ledger (`.harness/ledger.jsonl`) wired into CLI; comparison entries recorded.
- Acceptance: `pytest -q` green offline; live Anthropic/OpenAI runs skip without keys (documented, not faked).

## Runnable-state rule
Every milestone ends with `pytest -q` green and `python demo/run_demo.py` (from M5) reproducible.
