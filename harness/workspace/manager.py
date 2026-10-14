"""Isolated task workspaces: git worktree preferred, copy fallback."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Workspace:
    task_id: str
    path: Path
    base_commit: str
    evidence_ro: Path | None = None


class WorkspaceManager:
    def __init__(self, repo_root: Path, candidates_dir: Path | None = None):
        self.repo_root = Path(repo_root).resolve()
        self.candidates = Path(candidates_dir or (self.repo_root / "candidates")).resolve()

    def _base_commit(self) -> str:
        try:
            r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True)
            return r.stdout.strip() if r.returncode == 0 else "no-commit"
        except OSError:
            return "no-commit"

    def create(self, task_id: str) -> Workspace:
        dest = self.candidates / task_id / "repo"
        dest.parent.mkdir(parents=True, exist_ok=True)
        base = self._base_commit()
        wt_path = self.candidates / task_id / "repo.wt"
        # Prefer git worktree when repo has at least one commit.
        if base != "no-commit":
            r = subprocess.run(
                ["git", "worktree", "add", "--detach", str(wt_path)], cwd=self.repo_root, capture_output=True, text=True
            )
            if r.returncode == 0:
                return Workspace(task_id, wt_path.resolve(), base)
        # Fallback: copy tracked files (or everything except .git/candidates).
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.repo_root, dest, ignore=shutil.ignore_patterns(".git", "candidates", ".harness", "__pycache__"))
        return Workspace(task_id, dest.resolve(), base)

    def cleanup(self, ws: Workspace) -> None:
        r = subprocess.run(["git", "worktree", "remove", "--force", str(ws.path)], cwd=self.repo_root, capture_output=True, text=True)
        if r.returncode != 0 and ws.path.exists():
            # Only remove paths inside candidates/ (never repo root).
            if self.candidates.resolve() in ws.path.resolve().parents:
                shutil.rmtree(ws.path, ignore_errors=True)
