# ForgeLoop — Architecture Research — public Codex + self-improving tax agents

Scope: what public sources actually show. No proprietary internals claimed.
Status terms: **Verified** = directly observable in public docs/source; **Inferred** = reasonable
architectural reading; **Decision** = our independent implementation choice.

Primary: https://openai.com/index/building-self-improving-tax-agents-with-codex/
Platform: https://developers.openai.com/blog/codex-as-a-platform
Loop: https://openai.com/index/unrolling-the-codex-agent-loop/
App-server: https://openai.com/index/unlocking-the-codex-harness/
Source: https://github.com/openai/codex (Rust: `codex-rs/core`, `codex-rs/sandboxing`, `codex-rs/protocol`)
Instructions: https://developers.openai.com/codex/guides/agents-md
Skills: https://developers.openai.com/codex/skills and https://developers.openai.com/codex/concepts/customization

## 1. Agent execution loop and orchestration
- Capability: stateless turn loop — `instructions + tools + input` → model → tool-call or final
  message; tool result appended; re-query until termination message.
- Evidence: agent-loop article (Responses API `instructions/tools/input`, stateless requests, no
  `previous_response_id` for ZDR, prompt-caching prefix discipline).
- Status: Verified pattern.
- Decision: `harness/agent/engine.py` implements bounded loop with explicit limits
  (`max_iterations, wall_clock, token_budget, max_tool_calls, retries, max_output_bytes`).
  Static prefix (system + AGENTS.md + skill) first for cache-friendliness.
- Limitation: no `/responses/compact` latent compaction; MVP uses stop-and-summarize + budget stop.

## 2. Thread → Turn → Item + app-server
- Capability: durable thread container, one turn per user input, streaming item events,
  bidirectional approvals that pause the turn.
- Evidence: platform article + app-server article + OpenAgents teardown (Thread/Turn/Item JSON-RPC
  over stdio, TUI as client).
- Status: Verified.
- Decision: in-process dataclasses `Thread/Turn/Item` + JSONL event log; no daemon in MVP.
  Schema is JSON-compatible for future app-server split.
- Limitation: no remote attach, fork, or live interrupt streaming in MVP.

## 3. Tool discovery, calling, result handling
- Capability: model-visible menu (`ToolSpec`) ≠ runtime index (`ToolRegistry`); per-step router
  (`ToolRouter`) parses calls into `ToolInvocation`; hooks → approval → sandbox → execution;
  normalized output (`ResponseInputItem`) returns to model/history/events.
- Evidence: rememorio tool-route writeup, readoss tool-execution article, DeepWiki
  `ToolOrchestrator` (`orchestrator.rs`), `ToolExposure` Direct/Deferred/Hidden, parallel gating.
- Status: Verified from public source.
- Decision: `ToolRegistry` (name→handler + `exposure`, `parallel_safe`, `risk_tier`) +
  `ToolRouter.build per turn` + `ToolInvocation` context. Unknown names and bad payloads return
  model-visible errors, never silent exec.
- Limitation: no MCP client, no tool-search embedding; deferred tools listed, not vector-searched.

## 4. Context assembly and repo exploration
- Capability: AGENTS.md chain (global → repo root → cwd, one file per dir, 32 KiB cap) + skill
  progressive disclosure (metadata first, body on use, refs/scripts lazily).
- Evidence: AGENTS.md guide + `codex-rs/core/src/agents_md.rs`; skills docs + skill-creator sample.
- Status: Verified.
- Decision: `InstructionLoader` (git-root detection, override precedence, byte cap) and
  `SkillRegistry` (`.agents/skills/*/SKILL.md`). Content treated as untrusted data.
- Limitation: no memory store or compaction beyond budget stop in MVP.

## 5. Execution environment and workspace isolation
- Capability: per-task sandbox (Seatbelt macOS / bubblewrap+Landlock Linux /
  restricted-token Windows) + managed network proxy (allowlist, method policy, audit).
- Evidence: sandbox manager docs, core README, network-proxy README via readoss/DeepWiki.
- Status: Verified as Codex behavior; exact profiles are platform-specific.
- Decision: `WorkspaceManager` uses git worktree (fallback: directory copy); tool layer enforces
  path-jail + denylist + timeout + output cap. Arbitrary shell requires real OS isolation;
  otherwise disabled (see `docs/security_model.md`). Production evidence mounted read-only.
- Limitation: MVP has NO OS sandbox parity — explicitly not claimed (denylist ≠ sandbox).

## 6. Long-running tasks, resumability, checkpoints
- Capability: thread persistence, rollout logs, replay; session task queue (turn/review/compaction).
- Evidence: app-server article (persistence/reconnect), DeepWiki core (`Session`, SQ/EQ, rollout).
- Status: Verified at interface level; internals inferred.
- Decision: `TaskStore` JSON persistence per task (`task.json`, `events.jsonl`); resume replays
  history without re-executing completed tools.
- Limitation: no crash-consistent WAL; no remote resume.

## 7. Structured outputs and validation
- Capability: `codex exec` bounded non-interactive runs with structured output; graders for evals.
- Evidence: platform article (`codex exec`, SDK vs app-server guidance).
- Status: Verified.
- Decision: `AgentResult(status, summary, files_changed, diff, validation, usage)` dataclass;
  eval cases declare `method: exact|tolerance|script|model_graded` with thresholds.
- Limitation: model-graded evals require human spot-check; never sole proof.

## 8. Evaluation and regression
- Capability: targeted eval sets + regression suites; baseline-vs-candidate comparison before merge.
- Evidence: tax-agent article §2–3 (review rows → grouped findings → eval targets; targeted +
  regression rerun before candidate PR).
- Status: Verified workflow.
- Decision: `harness/evals/runner.py` runs `suites/*.yaml` against baseline and candidate checkouts,
  reports pass/fail + regression delta, preserves dataset/grader versions.
- Limitation: no distributed eval farm in MVP.

## 9. Human review and approval boundaries
- Capability: approval policy distinct from sandbox; Guardian auto-review; consequential writes
  (Relay rebook, tax filing) require explicit human approval.
- Evidence: orchestrator approval docs, Relay example, tax article (engineers own shipping).
- Status: Verified.
- Decision: `ApprovalPolicy` (`allow|prompt|forbid` per risk tier) + `REVIEW_REQUIRED → APPROVED`
  gate. Self-improvement loop never auto-merges.
- Limitation: no AI Guardian scorer in MVP; human + policy rules only.

## 10. Model-provider abstraction
- Capability: pluggable backends (OpenAI, LM Studio, Ollama) behind `SharedModelProvider`;
  streaming + retry + model discovery.
- Evidence: DeepWiki core agent system.
- Status: Verified interface; per-backend quirks inferred.
- Decision: `ModelProvider` ABC (`complete(messages, toolspec, ...) -> ProviderResult`);
  adapters: `openai_compat` (urllib, OpenAI-compatible `/chat/completions` with tools) and
  `mock` (deterministic scripted turns for offline tests). Tool-call capability probed per
  provider; non-tool models fall back to JSON-in-text parsing, clearly logged.
- Limitation: only OpenAI-compatible + mock ship in M2; second live backend (Anthropic/Ollama)
  is M6 and skipped without creds/binaries.
