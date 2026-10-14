# ForgeLoop — Limitations — known gaps (updated per milestone)

- OS sandbox: NO parity with Codex Seatbelt/bubblewrap. Denylist + jail + allowlist only; unrestricted
  exec disabled by default. Needs: platform sandbox backends + network proxy before untrusted exec.
- Provider coverage: M2 ships `mock` + `openai_compat` only. No Anthropic/Ollama adapter yet (M6);
  tool-call fallback for non-tool models is JSON-in-text (logged, weaker).
- No MCP client, no vector tool-search, no `/responses/compact` latent compaction, no Guardian AI scorer,
  no remote app-server/daemon, no multi-agent delegation.
- Resume is file-level (no WAL); eval farm is single-process.
- Windows-first paths; POSIX assumed compatible but CI only ran Windows + Python 3.13 here.
- Deps: `pyyaml`, `pytest` only — by design; any addition needs justification here.
