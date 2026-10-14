"""ForgeLoop local dashboard: stdlib ThreadingHTTPServer, localhost-only by default.

Read views render TaskStore / TraceStore / FindingStore / eval reports / ledger.
Exactly two action endpoints exist:
  POST /findings/<id>/approve  — same gate as Finding.approve()
  POST /runs                   — kind=eval (allowlisted suites/worktrees) or kind=demo
All POSTs require the per-process CSRF token and are audit-logged to the ledger.
"""
from __future__ import annotations

import json
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from . import views

REPO = Path(__file__).resolve().parent.parent.parent


class Dashboard:
    def __init__(self, repo: Path | str = REPO, csrf_token: str | None = None):
        self.repo = Path(repo).resolve()
        self.csrf = csrf_token or secrets.token_hex(16)
        self.tasks_root = self.repo / ".harness" / "tasks"
        self.traces_root = self.repo / ".harness" / "traces"
        self.findings_root = self.repo / ".harness" / "findings"
        self.ledger_path = self.repo / ".harness" / "ledger.jsonl"
        self.candidates = self.repo / "candidates"

    # ---- data helpers (read-only) ----
    def _tasks(self) -> List[Dict[str, Any]]:
        out = []
        if self.tasks_root.is_dir():
            for d in sorted(self.tasks_root.iterdir()):
                p = d / "task.json"
                if p.is_file():
                    try:
                        t = json.loads(p.read_text())
                        out.append({"id": t.get("id", d.name), "state": t.get("state", "?"),
                                    "description": t.get("description", ""), "updated": t.get("updated", "")})
                    except (OSError, json.JSONDecodeError):
                        continue
        return out

    def _task(self, tid: str) -> Dict[str, Any] | None:
        if not tid or "/" in tid or "\\" in tid or tid.startswith("."):
            return None
        p = self.tasks_root / tid / "task.json"
        if not p.is_file():
            return None
        try:
            t = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        evp = self.tasks_root / tid / "events.jsonl"
        t["events"] = []
        if evp.is_file():
            for line in evp.read_text().splitlines()[-50:]:
                try:
                    t["events"].append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return t

    def _candidates(self) -> List[Dict[str, Any]]:
        out = []
        if self.candidates.is_dir():
            for d in sorted(self.candidates.iterdir()):
                if not d.is_dir() or d.name == "README.md":
                    continue
                rep = d / "artifacts" / "eval_report.json"
                entry: Dict[str, Any] = {"id": d.name, "targeted": "?", "regression": "?"}
                if rep.is_file():
                    try:
                        r = json.loads(rep.read_text())
                        entry["targeted"] = f"{r['targeted']['passed']}/{r['targeted']['passed'] + r['targeted']['failed']}"
                        entry["regression"] = f"{r['regression']['passed']}/{r['regression']['passed'] + r['regression']['failed']}"
                    except (OSError, json.JSONDecodeError, KeyError):
                        pass
                out.append(entry)
        return out

    def _suites(self) -> List[str]:
        return sorted(str(p.relative_to(self.repo)) for p in self.repo.glob("**/suites/*.yaml")
                      if ".git" not in p.parts and "candidates" not in p.parts)

    def _reports(self) -> List[Dict[str, Any]]:
        reps = []
        for p in sorted(self.candidates.glob("*/artifacts/eval_report.json")):
            try:
                r = json.loads(p.read_text())
                for key in ("targeted", "regression"):
                    if key in r:
                        reps.append({"suite": r[key].get("suite", key), "passed": r[key].get("passed", 0),
                                     "failed": r[key].get("failed", 0)})
            except (OSError, json.JSONDecodeError):
                continue
        return reps

    def _findings(self) -> List[Dict[str, Any]]:
        from ..feedback.store import FindingStore

        try:
            return [vars(f) if hasattr(f, "__dict__") else f for f in FindingStore(self.findings_root).list()]
        except OSError:
            return []

    def _ledger(self) -> List[Dict[str, Any]]:
        from ..observe.ledger import Ledger

        try:
            return Ledger(self.ledger_path).read_all()
        except OSError:
            return []

    # ---- routing ----
    def route(self, method: str, path: str, body: Dict[str, str]) -> Tuple[int, str, str]:
        if method == "GET" and path == "/":
            from ..observe.ledger import Ledger

            try:
                summary = Ledger(self.ledger_path).summary()
            except OSError:
                summary = {}
            return 200, "text/html", views.overview(self._tasks(), summary, self._candidates())
        if method == "GET" and path == "/evals":
            return 200, "text/html", views.evals_page(self._suites(), self._reports(), self.csrf)
        if method == "GET" and path == "/findings":
            return 200, "text/html", views.findings_page(
                [{"id": f.id, "title": f.title, "status": f.status, "subsystem": f.subsystem}
                 for f in self._finding_objs()], self.csrf)
        if method == "GET" and path == "/ledger":
            return 200, "text/html", views.ledger_page(self._ledger())
        if method == "GET" and path.startswith("/tasks/"):
            t = self._task(path[len("/tasks/"):])
            if t is None:
                return 404, "text/plain", "unknown task"
            return 200, "text/html", views.task_detail(t, False, self.csrf)
        if method == "GET" and path.startswith("/traces/"):
            tid = path[len("/traces/"):]
            if not tid or "/" in tid or "\\" in tid or tid.startswith("."):
                return 404, "text/plain", "unknown trace"
            p = self.traces_root / f"{tid}.json"
            if not p.is_file():
                return 404, "text/plain", "unknown trace"
            try:
                return 200, "text/html", views.trace_page(tid, json.loads(p.read_text()))
            except (OSError, json.JSONDecodeError):
                return 500, "text/plain", "unreadable trace"
        if method == "POST" and path.startswith("/findings/") and path.endswith("/approve"):
            fid = path[len("/findings/"): -len("/approve")]
            return self._approve_finding(fid, body.get("csrf", ""))
        if method == "POST" and path == "/runs":
            return self._start_run(body)
        return 404, "text/plain", "not found"

    def _finding_objs(self) -> list:
        from ..feedback.store import FindingStore

        try:
            return FindingStore(self.findings_root).list()
        except OSError:
            return []

    def _check_csrf(self, token: str) -> bool:
        return bool(token) and secrets.compare_digest(token, self.csrf)

    def _audit(self, kind: str, meta: Dict[str, Any]) -> None:
        from ..observe.ledger import Ledger, RunRecord

        try:
            Ledger(self.ledger_path).append(RunRecord(kind=kind, provider="dashboard",
                                                      model="dashboard", usage={}, meta=meta))
        except OSError:
            pass

    def _approve_finding(self, fid: str, token: str) -> Tuple[int, str, str]:
        if not self._check_csrf(token):
            return 403, "text/plain", "bad csrf token"
        if not fid or "/" in fid or "\\" in fid or fid.startswith("."):
            return 404, "text/plain", "unknown finding"
        from ..feedback.store import FindingStore
        from ..feedback.findings import FindingError

        try:
            f = FindingStore(self.findings_root).approve(fid)
        except FileNotFoundError:
            return 404, "text/plain", "unknown finding"
        except FindingError as e:
            return 422, "text/html", views.result_page(f"approve {fid}", False, str(e))
        self._audit("finding_approve", {"finding": fid, "status": f.status})
        return 200, "text/html", views.result_page(f"approve {fid}", True, f"status: {f.status}")

    def _resolve_worktree(self, raw: str) -> Path | None:
        p = (self.repo / raw).resolve() if raw else None
        if p is None or self.repo.resolve() not in [p, *p.parents]:
            return None
        # Only candidate repos or the demo repo may be evaluation targets.
        rel = p.relative_to(self.repo.resolve())
        if rel.parts[:1] == ("candidates",) and rel.parts[-1] == "repo":
            return p
        if str(rel) == str(Path("demo/fair_rental_days/repo")):
            return p
        return None

    def _resolve_suite(self, raw: str) -> Path | None:
        p = (self.repo / raw).resolve() if raw else None
        if p is None or not p.is_file() or p.suffix != ".yaml":
            return None
        try:
            rel = p.relative_to(self.repo.resolve())
        except ValueError:
            return None
        if ".git" in rel.parts or "candidates" in rel.parts or "suites" not in rel.parts:
            return None
        return p

    def _start_run(self, body: Dict[str, str]) -> Tuple[int, str, str]:
        if not self._check_csrf(body.get("csrf", "")):
            return 403, "text/plain", "bad csrf token"
        kind = body.get("kind", "")
        t0 = time.time()
        if kind == "demo":
            try:
                proc = subprocess.run([sys.executable, "demo/run_demo.py"], cwd=self.repo,
                                      capture_output=True, text=True, timeout=300)
            except subprocess.TimeoutExpired:
                return 200, "text/html", views.result_page("demo run", False, "timed out after 300s")
            ok = proc.returncode == 0
            self._audit("demo_run", {"ok": ok, "latency_s": round(time.time() - t0, 2)})
            return 200, "text/html", views.result_page("demo run", ok, (proc.stdout + proc.stderr)[-8000:])
        if kind == "eval":
            suite = self._resolve_suite(body.get("suite", ""))
            wt = self._resolve_worktree(body.get("worktree", ""))
            if suite is None or wt is None:
                return 422, "text/html", views.result_page(
                    "eval run", False, "suite must be a repo suites/*.yaml and worktree a candidates/*/repo or the demo repo")
            from ..evals.runner import EvalIntegrityError, Runner

            try:
                rep = Runner().run(suite, wt)
            except EvalIntegrityError as e:
                return 200, "text/html", views.result_page("eval run", False, f"integrity failure: {e}")
            self._audit("eval_run", {"suite": rep.suite, "passed": rep.passed, "failed": rep.failed})
            return 200, "text/html", views.result_page("eval run", rep.failed == 0, rep.human())
        return 422, "text/plain", "unknown run kind"


class Handler(BaseHTTPRequestHandler):
    dashboard: Dashboard = None  # type: ignore[assignment]

    def log_message(self, *a: Any) -> None:  # keep test output clean
        pass

    def _send(self, code: int, ctype: str, body: str) -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        code, ctype, body = self.dashboard.route("GET", path, {})
        self._send(code, ctype, body)

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        raw = self.rfile.read(min(length, 65536)).decode(errors="replace")
        body = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
        code, ctype, body_text = self.dashboard.route("POST", path, body)
        self._send(code, ctype, body_text)

    def do_PUT(self) -> None:
        self._send(405, "text/plain", "method not allowed")

    def do_DELETE(self) -> None:
        self._send(405, "text/plain", "method not allowed")


def serve(host: str = "127.0.0.1", port: int = 8080, repo: Path | str = REPO) -> ThreadingHTTPServer:
    dash = Dashboard(repo)
    Handler.dashboard = dash  # type: ignore[attr-defined]
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"ForgeLoop dashboard on http://{host}:{srv.server_port} (localhost only)")
    return srv


def main(argv: List[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="forgeloop-dashboard")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args(argv)
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("refusing non-localhost bind without auth (see docs/security_model.md)")
    serve(a.host, a.port).serve_forever()


if __name__ == "__main__":
    main()
