# ForgeLoop — Security Model — permissions and trust boundaries

## Trust stance
Repo content, tool output, model text, and external docs are **untrusted data**. They never override
policy. Instruction files (`AGENTS.md`, `SKILL.md`) guide the model; enforcement lives in code.

## Filesystem
- Every tool resolves paths against `ToolContext.worktree`; `..` escapes and absolute paths outside
  the worktree are rejected (`SecurityError`). Verified by tests (`test_jail_escape`, `test_evidence_readonly`).
- Evidence (`evidence/`) and eval expectations (`evals/expected*`, `suites/*.yaml`) are opened read-only;
  fixture SHA256 is checked at run start and end (`test_eval_immutable` fails the run on mismatch).
- Candidate may write only `repo/` + `artifacts/` + its own logs.

## Commands
- **A denylist is NOT a sandbox** (explicit non-claim). It is a backstop only.
- `exec_approved`/`run_tests`/`lint` run an **allowlist**: `python -m pytest <worktree-rel>`,
  `python -m py_compile <file>`, `git status|diff -- <path>`. Anything else → rejected unless
  `approval=granted` AND `HARNESS_ALLOW_UNRESTRICTED=1` AND a documented OS sandbox exists.
- Default in this environment: unrestricted exec is **disabled** (no OS sandbox verified).
  The runner raises `SecurityError("unrestricted execution disabled")` rather than silently
  running `subprocess` with full privileges.
- Timeouts (default 60 s, max 300 s) and output caps (default 64 KiB, truncation head+tail) on all exec.

## Approvals
- Tiers: `read` (auto) · `edit` (auto inside worktree, prompt outside — outside always denied in MVP) ·
  `exec` (auto iff allowlisted, else prompt) · `privileged` (prompt; default forbid in non-interactive).
- Task completion gate `REVIEW_REQUIRED → APPROVED` is human (or explicit policy file); the loop never
  auto-merges or deploys.

## Secrets and audit
- Redaction of `api_key, token, secret, password, authorization` in traces/logs; retention: traces are
  local JSONL with no external exfil; live keys only from env, never written to artifacts.
- Every tool call is appended to `events.jsonl` (who/what/args-hash/result-truncated/latency).

## Prompt injection
- Tool results are wrapped as `tool_result` messages, never as `system` instructions; the engine only
  honors `tool_calls` matching registered specs. Tests feed a malicious file (`Ignore previous
  instructions…`) and assert no policy override.

## Interrupt/failure safety
- Timeouts kill the child process group; partial edits leave `task.state=FAILED` with reason;
  `resume()` never re-applies a completed edit blindly (idempotency via content hash).
