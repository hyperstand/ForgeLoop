"""Persistent task lifecycle. Completion needs recorded validation, not model prose."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


STATES = ("CREATED", "INVESTIGATING", "PLANNED", "IMPLEMENTING", "VALIDATING",
          "REVIEW_REQUIRED", "APPROVED", "COMPLETED", "FAILED", "CANCELLED", "BLOCKED")

EDGES: Dict[str, List[str]] = {
    "CREATED": ["INVESTIGATING", "CANCELLED"],
    "INVESTIGATING": ["PLANNED", "BLOCKED", "FAILED", "CANCELLED"],
    "PLANNED": ["IMPLEMENTING", "BLOCKED", "FAILED", "CANCELLED"],
    "IMPLEMENTING": ["VALIDATING", "BLOCKED", "FAILED"],
    "VALIDATING": ["REVIEW_REQUIRED", "FAILED", "BLOCKED"],
    "REVIEW_REQUIRED": ["APPROVED", "FAILED", "BLOCKED"],
    "APPROVED": ["COMPLETED", "FAILED"],
    "BLOCKED": ["INVESTIGATING", "PLANNED", "CANCELLED"],
    "FAILED": ["INVESTIGATING"],
    "CANCELLED": [],
    "COMPLETED": [],
}


class TaskError(Exception):
    pass


@dataclass
class Task:
    id: str
    description: str
    success_criteria: List[str] = field(default_factory=list)
    state: str = "CREATED"
    plan: str = ""
    findings: List[str] = field(default_factory=list)
    tool_activity: List[Dict[str, Any]] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    files_changed: List[str] = field(default_factory=list)
    diff: str = ""
    failure_reason: str = ""
    updated: str = ""

    def touch(self) -> None:
        self.updated = datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, root: str | Path = ".harness/tasks"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, task_id: str) -> Path:
        d = self.root / task_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create(self, task: Task) -> Task:
        task.touch()
        self.save(task)
        self._log(task.id, {"ev": "created", "state": task.state})
        return task

    def save(self, task: Task) -> None:
        task.touch()
        (self._dir(task.id) / "task.json").write_text(json.dumps(asdict(task), indent=2))

    def load(self, task_id: str) -> Task:
        p = self.root / task_id / "task.json"
        if not p.exists():
            raise TaskError(f"unknown task: {task_id}")
        d = json.loads(p.read_text())
        return Task(**d)

    def transition(self, task: Task, to: str, reason: str = "") -> Task:
        if to not in STATES:
            raise TaskError(f"unknown state: {to}")
        if to not in EDGES.get(task.state, []):
            raise TaskError(f"illegal transition {task.state} -> {to}")
        if to == "APPROVED" and not task.validation.get("passed"):
            raise TaskError("APPROVED requires validation.passed=true")
        task.state = to
        if reason and to in ("FAILED", "BLOCKED", "CANCELLED"):
            task.failure_reason = reason
        self.save(task)
        self._log(task.id, {"ev": "transition", "state": to, "reason": reason})
        return task

    def record_tool(self, task: Task, name: str, args: Dict[str, Any], result: Any) -> None:
        task.tool_activity.append({"tool": name, "args": args, "result": str(result)[:2000]})
        self.save(task)
        self._log(task.id, {"ev": "tool", "tool": name})

    def _log(self, task_id: str, ev: Dict[str, Any]) -> None:
        with open(self._dir(task_id) / "events.jsonl", "a") as f:
            f.write(json.dumps({**ev, "ts": datetime.now(timezone.utc).isoformat()}) + "\n")

    def resume(self, task_id: str) -> Task:
        """Reload persisted history; never re-executes tools."""
        return self.load(task_id)
