"""Security policy: path jail, denylist (backstop only), allowlisted exec."""
from __future__ import annotations

import os
import re
from pathlib import Path


class SecurityError(Exception):
    pass


# Backstop patterns — NOT a sandbox. Unrestricted exec stays disabled without OS isolation.
DENYLIST = [
    r"rm\s+-rf\s+/(^ )", r"mkfs", r":\(\)\s*\{", r"shutdown", r"reboot",
    r"DROP\s+DATABASE", r"pg_drop", r"--no-preserve-root",
]

ALLOWLIST_PREFIXES = (
    ("python", "-m", "pytest"),
    ("python", "-m", "py_compile"),
    ("git", "status"),
    ("git", "diff"),
)


def resolve_in_worktree(worktree: Path, rel: str) -> Path:
    p = (worktree / rel).resolve()
    root = worktree.resolve()
    if p != root and root not in p.parents:
        raise SecurityError(f"path escapes worktree: {rel}")
    return p


def check_deny(cmd: str) -> None:
    for pat in DENYLIST:
        if re.search(pat, cmd, re.IGNORECASE):
            raise SecurityError(f"denied command pattern: {pat}")


def is_allowlisted(argv: list[str]) -> bool:
    t = tuple(argv)
    return any(t[: len(p)] == p for p in ALLOWLIST_PREFIXES)


def check_exec(argv: list[str], unrestricted_allowed: bool = False) -> None:
    check_deny(" ".join(argv))
    if is_allowlisted(argv):
        return
    if not unrestricted_allowed:
        raise SecurityError("unrestricted execution disabled: no OS sandbox configured")


def redact(text: str) -> str:
    return re.sub(r"(?i)(api_key|token|secret|password|authorization)([\"'\s:=]+)([^\s\"',}]+)", r"\1\2***", text)


def enforce_output_cap(text: str, cap: int = 65536) -> str:
    if len(text) <= cap:
        return text
    head = cap * 3 // 4
    return text[:head] + f"\n...[truncated {len(text) - cap} bytes]...\n" + text[-cap // 4:]
