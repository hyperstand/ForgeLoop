"""Built-in tools with jail, timeout, and output-cap enforcement."""
from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any, Dict

from ..security.policy import check_exec, enforce_output_cap, resolve_in_worktree
from .registry import ToolContext, ToolDef, ToolError, ToolRegistry


def _run(argv: list[str], cwd: Path, timeout_s: float, cap: int) -> Dict[str, Any]:
    check_exec(argv, unrestricted_allowed=False)
    try:
        p = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise ToolError(f"command timed out after {timeout_s}s: {' '.join(argv)}")
    out = enforce_output_cap((p.stdout or "") + (p.stderr or ""), cap)
    return {"exit": p.returncode, "output": out}


def _t_list_files(a: Dict[str, Any], ctx: ToolContext):
    root = resolve_in_worktree(ctx.worktree, a.get("root", "."))
    pat = a.get("glob", "**/*")
    out, n = [], 0
    for p in sorted(root.rglob("*")):
        if p.is_file() and fnmatch.fnmatch(p.name, pat.split("/")[-1]):
            out.append(str(p.relative_to(ctx.worktree)))
            n += 1
            if n >= int(a.get("max", 200)):
                break
    return {"files": out}


def _t_read_file(a: Dict[str, Any], ctx: ToolContext):
    p = resolve_in_worktree(ctx.worktree, a["path"])
    if not p.is_file():
        raise ToolError(f"not a file: {a['path']}")
    data = p.read_bytes()[: int(a.get("max_bytes", 65536))]
    return {"path": a["path"], "content": data.decode(errors="replace")}


def _t_search(a: Dict[str, Any], ctx: ToolContext):
    rx = re.compile(a["pattern"])
    hits = []
    for p in ctx.worktree.rglob("*"):
        if not p.is_file() or len(hits) >= int(a.get("max_hits", 50)):
            continue
        if ".git" in p.parts:
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append({"file": str(p.relative_to(ctx.worktree)), "line": i, "text": line[:300]})
                if len(hits) >= int(a.get("max_hits", 50)):
                    break
    return {"hits": hits}


def _t_git_status(a: Dict[str, Any], ctx: ToolContext):
    return _run(["git", "status", "--porcelain"], ctx.worktree, ctx.timeout_s, ctx.max_output_bytes)


def _t_git_diff(a: Dict[str, Any], ctx: ToolContext):
    argv = ["git", "diff", "--"]
    if a.get("path"):
        resolve_in_worktree(ctx.worktree, a["path"])
        argv.append(a["path"])
    return _run(argv, ctx.worktree, ctx.timeout_s, ctx.max_output_bytes)


def _t_edit_file(a: Dict[str, Any], ctx: ToolContext):
    p = resolve_in_worktree(ctx.worktree, a["path"])
    if not p.is_file():
        raise ToolError(f"not a file: {a['path']}")
    text = p.read_text()
    old, new = a["old_string"], a["new_string"]
    if old not in text:
        raise ToolError("old_string not found")
    if not a.get("replace_all", False) and text.count(old) > 1:
        raise ToolError("old_string matches multiple times; use replace_all or more context")
    p.write_text(text.replace(old, new) if a.get("replace_all") else text.replace(old, new, 1))
    return {"path": a["path"], "ok": True}


def _t_run_tests(a: Dict[str, Any], ctx: ToolContext):
    target = a.get("target", "tests")
    # target must stay inside worktree; pytest invoked as module (allowlisted)
    if ".." in Path(target).parts or Path(target).is_absolute():
        raise ToolError("target escapes worktree")
    return _run(["python", "-m", "pytest", target, "-q"], ctx.worktree, float(a.get("timeout_s", 120)), ctx.max_output_bytes)


def _t_lint(a: Dict[str, Any], ctx: ToolContext):
    resolve_in_worktree(ctx.worktree, a["path"])
    return _run(["python", "-m", "py_compile", a["path"]], ctx.worktree, ctx.timeout_s, ctx.max_output_bytes)


def _t_exec(a: Dict[str, Any], ctx: ToolContext):
    import shlex

    argv = shlex.split(a["command"])
    if not argv:
        raise ToolError("empty command")
    return _run(argv, ctx.worktree, float(a.get("timeout_s", 60)), ctx.max_output_bytes)


def _t_run_eval(a: Dict[str, Any], ctx: ToolContext):
    from ..evals.runner import Runner  # lazy: avoids import cycle

    rep = Runner().run(a["suite"], Path(a.get("worktree", str(ctx.worktree))))
    return {"report": rep.to_dict()}


def _t_task_status(a: Dict[str, Any], ctx: ToolContext):
    from ..tasks.store import TaskStore  # lazy

    st = TaskStore(a.get("store", ".harness/tasks")).load(a["task_id"])
    return {"task_id": st.id, "state": st.state, "updated": st.updated}


DEFS = [
    ToolDef("list_files", "List files under worktree", {"type": "object", "properties": {"root": {"type": "string", "default": "."}, "glob": {"type": "string", "default": "**/*"}, "max": {"type": "integer", "default": 200}}}, _t_list_files),
    ToolDef("read_file", "Read a worktree file", {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer", "default": 65536}}}, _t_read_file),
    ToolDef("search", "Regex search worktree", {"type": "object", "required": ["pattern"], "properties": {"pattern": {"type": "string"}, "max_hits": {"type": "integer", "default": 50}}}, _t_search),
    ToolDef("git_status", "git status porcelain", {"type": "object", "properties": {}}, _t_git_status),
    ToolDef("git_diff", "git diff", {"type": "object", "properties": {"path": {"type": "string"}}}, _t_git_diff),
    ToolDef("edit_file", "Scoped file edit", {"type": "object", "required": ["path", "old_string", "new_string"], "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}, "replace_all": {"type": "boolean", "default": False}}}, _t_edit_file, risk_tier="edit", parallel_safe=False),
    ToolDef("run_tests", "Run pytest target (allowlisted)", {"type": "object", "properties": {"target": {"type": "string", "default": "tests"}, "timeout_s": {"type": "number", "default": 120}}}, _t_run_tests, risk_tier="exec", parallel_safe=False),
    ToolDef("lint", "py_compile a file", {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}, _t_lint, risk_tier="exec"),
    ToolDef("exec_approved", "Allowlisted command only", {"type": "object", "required": ["command"], "properties": {"command": {"type": "string"}, "timeout_s": {"type": "number", "default": 60}}}, _t_exec, risk_tier="exec", parallel_safe=False),
    ToolDef("run_eval", "Run an eval suite", {"type": "object", "required": ["suite"], "properties": {"suite": {"type": "string"}, "worktree": {"type": "string"}}}, _t_run_eval, risk_tier="read"),
    ToolDef("task_status", "Load task state", {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}, "store": {"type": "string", "default": ".harness/tasks"}}}, _t_task_status),
]


def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for d in DEFS:
        reg.register(d)
    return reg
