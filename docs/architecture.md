# Architecture (M1) — component contracts

Modules map 1:1 to `harness/`. All cross-module data uses typed dataclasses, JSON-serializable.

## A. `providers/base.py` — ModelProvider ABC
- `ChatMessage(role, content, tool_calls?, tool_call_id?)`, `ToolSpec(name, description, schema)`,
  `ProviderResult(message, usage{tokens_in,out}, model, raw?)`, `ProviderError(code, message, retryable)`.
- `ModelProvider.complete(messages, tools, timeout_s, **params) -> ProviderResult`. Streaming optional
  (`stream_complete` yields deltas; default buffers `complete`).
- `capabilities() -> {tool_calling: bool, streaming: bool, max_context: int|None}`.
- Errors normalized: auth / rate-limit (retryable) / timeout / bad-request / transport. Never raises SDK types.
- Adapters: `openai_compat.OpenAICompatProvider` (urllib POST `{base_url}/chat/completions`,
  OpenAI tool schema; env `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `HARNESS_MODEL`), `mock.MockProvider`
  (scripted `ProviderResult` queue for deterministic tests/demo).

## B. `agent/engine.py` — bounded loop
- `EngineConfig(max_iterations=12, wall_clock_s=300, token_budget=60000, max_tool_calls=30,
  max_output_bytes=65536, retries=2)`, `AgentResult(status, summary, files_changed, diff,
  validation, usage, trace_id)`.
- Status: `completed | failed | blocked_needs_approval | blocked_needs_clarification | budget_exceeded`.
- Flow per turn: load instructions → inspect (list/read/search via tools) → plan (model) →
  tool-call validate → execute → append result → repeat → run checks → structured result.
- Model text is untrusted: only `tool_calls` matching registered specs execute; everything else is prose.

## C. `tools/` — registry + router + builtins
- `ToolDef(name, description, schema{jsonschema-subset}, risk_tier, exposure, parallel_safe)`.
- `ToolRegistry.register/def get/list_specs`; `ToolRouter.dispatch(name, args, ctx)` validates
  required fields/types, unknown tools → model-visible error.
- Risk tiers: `read` (list/read/search/git/diff, task_status, run_eval) · `edit` (edit_file in worktree)
  · `exec` (run_tests/lint/exec_approved — allowlisted cmds only) · `privileged` (always prompt/forbid).
- Builtins (10): `list_files, read_file, search, git_status, git_diff, edit_file, run_tests,
  lint, exec_approved, run_eval, task_status` (11 incl. status; registry enforces jail/timeout/caps).
- `ToolContext(worktree, evidence_ro, task_id, approvals, budget)`.

## D. `workspace/manager.py`
- `Workspace(task_id, path, base_commit, evidence_ro, created)`; `create_task_workspace(task_id)`
  prefers `git worktree add --detach <base>`; fallback: copy tracked files to `candidates/<id>/repo/`.
- Guarantees: unique id, recorded base commit, per-task logs/artifacts, `cleanup()` removes worktree
  (never deletes evidence or repo root). Evidence dir bind is read-only by convention + verified
  (write probe refused; see security tests).

## E. `tasks/` — lifecycle
- States: `CREATED → INVESTIGATING → PLANNED → IMPLEMENTING → VALIDATING → REVIEW_REQUIRED →
  APPROVED → COMPLETED`, plus `FAILED, CANCELLED, BLOCKED`.
- `TaskStore(root)` persists `task.json` + `events.jsonl`; `transition(task, to)` validates edges;
  `resume(task_id)` reloads history. Completion requires recorded validation pass, not model prose.

## F. `traces/` — schema v1
- `Trace(id, task_id, ts, provider, model, params, context_refs, tool_calls[], evidence[],
  intermediates[], prediction, correction, outcome, errors[], usage, code_versions)`.
- `TraceStore.append/get`; secrets redacted (`api_key|token|secret|password`); raw traces append-only,
  review records separate (`feedback/`).

## G. `feedback/` — reviews → findings → eval cases
- `ReviewRecord(trace_id, predicted, corrected, evidence, category, actionable, confidence, reviewer)`.
  Categories: `missing_capability, incorrect_retrieval, wrong_tool, schema_mismatch, mapping_error,
  business_rule, unsupported_reasoning, grader_defect, workflow_noise, insufficient_evidence`.
- `Finding(id, title, subsystem, traces[], repro, expected, actual, hypothesis, frequency, impact,
  confidence, counterexamples, eval_criteria, status=draft|approved|rejected)`. Single corrections
  never auto-become tasks; `approve()` is explicit.
- `evalgen.finding_to_eval_case(finding)` emits versioned `EvalCase`.

## H. `evals/` — runner + graders
- `EvalCase(id, fixture, expected, constraints, method, pass_criteria, category, dataset_version)`,
  `EvalSuite(cases[], regression[])`; methods: `exact | tolerance | script | model_graded(needs human check)`.
- `Runner.run(suite, worktree)` returns machine JSON + human markdown; `compare(baseline, candidate)`
  flags fixed/regressed. Fixture SHA256 verified before run; expected files opened read-only.

## I. Skills + instructions
- `skills/loader.py`: `SkillRegistry.discover(root)` reads `.agents/skills/*/SKILL.md`
  (frontmatter `name, description`); `select(task)` returns metadata-first, body on match.
- `InstructionLoader`: git-root→cwd `AGENTS.md`/`AGENTS.override.md` chain, 32 KiB cap.

## J. Security boundaries (summary; full: security_model.md)
- Path-jail (all writes resolved inside worktree), denylist, timeouts, output caps, tiered approvals.
- Arbitrary shell disabled without OS isolation; allowlisted `python -m pytest …`, `python -m py_compile`,
  `git status/diff` only inside worktree.
