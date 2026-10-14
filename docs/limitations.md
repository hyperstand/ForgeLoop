# ForgeLoop — Limitations — known gaps (updated per milestone)

- OS sandbox: NO parity with Codex Seatbelt/bubblewrap. Denylist + jail + allowlist only; unrestricted
  exec disabled by default. Needs: platform sandbox backends + network proxy before untrusted exec.
- Provider coverage: `mock` + `openai_compat` + `anthropic` adapters ship (M6).
  Anthropic uses its native Messages API (`x-api-key`, content blocks, `tool_use`/`tool_result`);
  live Anthropic/OpenAI runs are untested here (no keys in this environment) — live tests skip.
  No Ollama/local adapter yet; tool-call fallback for non-tool models is JSON-in-text (logged, weaker).
- No MCP client, no vector tool-search, no `/responses/compact` latent compaction, no Guardian AI scorer,
  no remote app-server/daemon, no multi-agent delegation.
- Resume is checkpoint-based (`AgentEngine.run(..., checkpoint_path, resume_from)` replays
  messages without re-executing tools; `TaskStore.resume` restores lifecycle state). No WAL; eval farm is single-process.
- Windows-first paths; POSIX assumed compatible but CI only ran Windows + Python 3.13 here.
- Deps: `pyyaml`, `pytest` only — by design; any addition needs justification here.
