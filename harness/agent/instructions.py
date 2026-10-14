"""AGENTS.md chained discovery: git-root -> cwd, override precedence, byte cap."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git_root(cwd: Path) -> Path | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True)
        return Path(r.stdout.strip()).resolve() if r.returncode == 0 else None
    except OSError:
        return None


def load_instructions(cwd: Path, max_bytes: int = 32768) -> str:
    cwd = Path(cwd).resolve()
    root = _git_root(cwd) or cwd
    chain: list[Path] = []
    cur = cwd
    while True:
        chain.append(cur)
        if cur == root or cur.parent == cur:
            break
        cur = cur.parent
    parts: list[str] = []
    used = 0
    for d in reversed(chain):
        for cand in (d / "AGENTS.override.md", d / "AGENTS.md"):
            if cand.is_file():
                text = cand.read_text().strip()
                if text:
                    parts.append(text)
                    used += len(text.encode())
                    break
        if used >= max_bytes:
            break
    return "\n\n--- project-doc ---\n\n".join(parts)[:max_bytes]
