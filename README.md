# ForgeLoop

**A model-agnostic coding-agent harness with a test-driven self-improvement loop.**

ForgeLoop is an extensible engineering platform for building, running, evaluating, and improving AI coding agents. It combines controlled agent execution, tool orchestration, isolated workspaces, execution traces, regression evaluations, and human-reviewed improvement workflows.

Inspired by publicly documented Codex architecture and OpenAI's *Building self-improving tax agents with Codex*, ForgeLoop explores how to build an independent coding-agent harness without coupling its core architecture to a single LLM provider.

> **Project status:** M1–M6 implemented and verified offline (`pytest -q` → 54 passed; `python demo/run_demo.py` reproduces end to end). Live Anthropic/OpenAI runs are untested here (no keys) — live tests skip. Remaining: Ollama/local adapter, live provider verification.

## Why ForgeLoop?

An LLM that can generate code is not, by itself, a reliable engineering system.

A practical coding agent also needs to understand a repository, use tools safely, manage execution state, verify its changes, and provide evidence that its work is correct.

ForgeLoop is designed to provide that engineering infrastructure.

Its central principle is:

**Every improvement should be traceable, testable, and reviewable.**

## Core capabilities

- **Model-agnostic architecture** — separate model-provider integrations from the agent execution engine.
- **Controlled agent execution** — bounded iterations, execution timeouts, tool limits, and structured results.
- **Tool orchestration** — typed tool definitions, argument validation, explicit permissions, and controlled execution.
- **Workspace isolation** — dedicated task workspaces and Git worktrees where supported.
- **Execution tracing** — record model interactions, tool calls, outcomes, errors, and validation evidence.
- **Evaluation and regression testing** — compare candidate changes against reproducible evaluation datasets.
- **Feedback-driven improvement** — convert reviewed failures into findings, evaluation cases, and bounded engineering tasks.
- **Human approval** — require review before accepting changes into the main codebase.
- **Reusable skills** — organize repository investigation, debugging, testing, and code-review procedures into reusable instructions.

## Architecture

```text
Engineering Task
       |
       v
Task Orchestrator
       |
       v
Agent Execution Engine
       |
       +---- Model Provider
       |       +---- OpenAI-compatible API
       |       +---- Anthropic Messages API
       |       +---- Mock Provider
       |       +---- Future Providers (Ollama/local planned)
       |
       +---- Tool Registry
       |       +---- Repository Inspection
       |       +---- File Editing
       |       +---- Testing and Evaluation
       |
       +---- Isolated Workspace
       |
       v
Execution Traces
       |
       v
Failure Analysis
       |
       v
Reviewed Finding
       |
       v
Evaluation Case
       |
       v
Bounded Coding Task
       |
       v
Targeted + Regression Tests
       |
       v
Reviewable Patch
       |
       v
Human Approval
```

The improvement loop operates alongside the coding agent. It does not automatically treat every user correction as a software defect or allow an agent to approve its own changes.

## Technology stack

| Component | Initial approach |
|---|---|
| Language | Python |
| Model integration | OpenAI-compatible API + Anthropic Messages API (config-driven, swappable) |
| Offline development | Deterministic mock provider |
| Testing | pytest |
| Version control | Git |
| Task and trace persistence | Structured local files |
| Evaluation datasets | Versioned fixtures |
| Workspace management | Git worktrees, with a controlled fallback |
| Security | Explicit tool permissions, filesystem boundaries, timeouts, and OS-level isolation required for arbitrary command execution (unrestricted exec is disabled until a verified OS sandbox backend exists — see `docs/security_model.md` and `docs/limitations.md`) |

The initial implementation is designed to run without live model credentials when using the mock provider.

## Self-improvement workflow

ForgeLoop follows a controlled engineering cycle:

1. **Observe** — capture execution traces and relevant evidence.
2. **Review** — compare the original result with a verified correction.
3. **Diagnose** — classify the failure and investigate its root cause.
4. **Evaluate** — turn an approved finding into a reproducible regression case.
5. **Implement** — create a bounded coding task with explicit acceptance criteria.
6. **Validate** — run targeted evaluations and existing regression tests.
7. **Review** — generate a patch and engineering report for human approval.
8. **Improve** — retain the verified evaluation case for future runs.

This process aims to improve the surrounding engineering system through verified changes, rather than relying solely on prompt changes or model memory.

## Example project structure

```text
ForgeLoop/
├── AGENTS.md
├── README.md
├── requirements.txt
├── harness/
│   ├── providers/
│   ├── agent/
│   ├── tools/
│   ├── workspace/
│   ├── tasks/
│   ├── traces/
│   ├── feedback/
│   ├── evals/
│   ├── skills/
│   └── security/
├── .agents/
│   └── skills/
├── docs/
│   ├── architecture_research.md
│   ├── current_state_audit.md
│   ├── architecture.md
│   ├── implementation_plan.md
│   ├── security_model.md
│   ├── evaluation_design.md
│   ├── operations.md
│   └── limitations.md
├── tests/
├── demo/
│   └── fair_rental_days/
├── examples/
└── candidates/
```

`pyproject.toml` / `config/` are not present; installation uses `requirements.txt` (`pyyaml`, `pytest`). The Python import package remains `harness`.

## Development roadmap

- [x] **M1 — Research and architecture:** document public references, system design, contracts, and security boundaries.
- [x] **M2 — Minimal harness:** implement providers, the bounded agent loop, tools, workspaces, and task lifecycle.
- [x] **M3 — Evaluation infrastructure:** add trace persistence, evaluation datasets, baseline comparison, and regression reporting.
- [x] **M4 — Feedback workflow:** implement reviewed corrections, findings, approval gates, and evaluation generation.
- [x] **M5 — End-to-end demonstration:** demonstrate a verified failure-to-fix workflow with a reviewable patch.
- [x] **M6 — Hardening (shipped; live runs pending creds):** Anthropic adapter + provider factory, model comparison, checkpoint resume, security test suite, run ledger observability. Ollama/local adapter and live provider verification remain open.

Milestones should be marked complete only after their acceptance criteria have been verified.

## Quick start

Prerequisites:

- Python 3.11 or later
- Git
- pytest

Create and activate a virtual environment:

```powershell
cd D:\llm_new
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the offline test suite:

```powershell
python -m pytest -q
```

No live API credentials should be required for the mock-provider tests.

Run the end-to-end demonstration:

```powershell
python demo/run_demo.py
```

Configure model providers via `examples/models.yaml` (default: `mock`; `openai_compat` reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `HARNESS_MODEL`; `anthropic` reads `ANTHROPIC_API_KEY` and `HARNESS_ANTHROPIC_MODEL`). Provider selection is config-driven — switching models never requires orchestrator changes.

Compare two eval reports (e.g. baseline vs candidate):

```powershell
python -m harness.cli compare --baseline artifacts/baseline_report.json --candidate artifacts/eval_report.json
```

Every `task-run` / `eval-run` appends cost and latency records to `.harness/ledger.jsonl` for model-comparison audits.

## Dashboard

A stdlib-only local web UI (no extra dependencies):

```powershell
python -m harness.cli serve --port 8080
```

Browse tasks, eval reports, findings, redacted traces, and the run ledger at `http://127.0.0.1:8080`.
Two actions are available in the browser: approving eligible findings and triggering eval/demo runs —
both CSRF-protected, localhost-only, audit-logged, and bound by the same validation gates as the CLI.
See `docs/operations.md` for details.

## Security model

ForgeLoop is designed around explicit execution permissions and independent validation.

- Repository files, tool output, and external documents are treated as untrusted input.
- Agent tasks operate within designated workspaces.
- Evaluation expectations and production evidence are protected from agent modifications.
- Tool execution is subject to argument validation, permissions, timeouts, and output limits.
- Arbitrary shell execution requires genuine operating-system isolation.
- Failed validation prevents task approval.
- Changes are presented for human review before being accepted into the main codebase.
- Production deployment is outside the autonomous improvement loop.

A command denylist alone is not considered a sufficient sandbox.

## Design principles

1. **Model independence:** provider integrations should not dictate the entire architecture.
2. **Evidence over claims:** task completion must be supported by observable results.
3. **Tests before trust:** candidate improvements must pass relevant regression checks.
4. **Isolation by default:** tasks should not have unrestricted access to the host environment.
5. **Explicit approval:** risky actions and code acceptance require appropriate authorization.
6. **Incremental implementation:** every milestone should leave the project runnable and tested.
7. **Honest reporting:** distinguish implemented capabilities from planned features.

## References

- [Building self-improving tax agents with Codex](https://openai.com/index/building-self-improving-tax-agents-with-codex/)
- [Codex as a platform](https://developers.openai.com/blog/codex-as-a-platform)

ForgeLoop is an independent implementation inspired by publicly documented engineering patterns. It is not an official OpenAI product and does not claim to reproduce proprietary Codex internals.

## License

To be determined.
