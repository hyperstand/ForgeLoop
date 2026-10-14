"""Dashboard tests: views, CSRF, approve gate, run allowlist, traversal, XSS."""
import json
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from harness.feedback.findings import group_reviews
from harness.feedback.store import FindingStore
from harness.tasks.store import Task, TaskStore
from harness.traces.schema import Trace, TraceStore
from harness.web.server import REPO, Dashboard, Handler

DEMO = Path("demo/fair_rental_days")


@pytest.fixture()
def dash(tmp_path):
    d = Dashboard(tmp_path)
    ts = TaskStore(d.tasks_root)
    t = ts.create(Task(id="T1", description="demo task"))
    ts.transition(t, "INVESTIGATING")
    TraceStore(d.traces_root).append(Trace(id="tr1", task_id="T1", prediction={"a": 0}))
    f = group_reviews("FIND-WEB-1", "web finding <script>alert(1)</script>", "s", ["tr1"],
                      repro=["r"], expected="e", actual="a", hypothesis="h",
                      confidence=0.8, eval_criteria="suite passes")
    FindingStore(d.findings_root).save(f)
    return d


def test_overview_renders_tasks_and_nav(dash):
    code, ctype, body = dash.route("GET", "/", {})
    assert code == 200 and "text/html" in ctype
    assert "T1" in body and "/evals" in body and "/findings" in body


def test_task_and_trace_pages(dash):
    assert dash.route("GET", "/tasks/T1", {})[0] == 200
    assert dash.route("GET", "/tasks/nope", {})[0] == 404
    assert dash.route("GET", "/tasks/../x", {})[0] == 404
    code, _, body = dash.route("GET", "/traces/tr1", {})
    assert code == 200 and "&quot;a&quot;: 0" in body  # JSON is HTML-escaped
    assert dash.route("GET", "/traces/../../etc", {})[0] == 404
    assert dash.route("GET", "/nope", {})[0] == 404


def test_xss_escaped_in_findings(dash):
    _, _, body = dash.route("GET", "/findings", {})
    assert "<script>" not in body and "&lt;script&gt;" in body


def test_csrf_tokens_unique_per_process(tmp_path):
    assert Dashboard(tmp_path).csrf != Dashboard(tmp_path).csrf


def test_approve_needs_valid_csrf(dash):
    assert dash.route("POST", "/findings/FIND-WEB-1/approve", {})[0] == 403
    assert dash.route("POST", "/findings/FIND-WEB-1/approve", {"csrf": "wrong"})[0] == 403
    assert dash.route("POST", "/findings/FIND-WEB-1/approve", {"csrf": dash.csrf})[0] == 200
    assert FindingStore(dash.findings_root).load("FIND-WEB-1").status == "approved"


def test_approve_rejects_unknown_and_traversal(dash):
    assert dash.route("POST", "/findings/NOPE/approve", {"csrf": dash.csrf})[0] == 404
    assert dash.route("POST", "/findings/../x/approve", {"csrf": dash.csrf})[0] == 404


def test_approve_audited_to_ledger(dash):
    dash.route("POST", "/findings/FIND-WEB-1/approve", {"csrf": dash.csrf})
    rows = (dash.ledger_path.read_text().splitlines())
    assert any("finding_approve" in r for r in rows)


def test_runs_require_csrf_and_allowlisted_paths():
    d = Dashboard(REPO)
    assert d.route("POST", "/runs", {})[0] == 403
    bad = {"csrf": d.csrf, "kind": "eval", "suite": str(DEMO / "suites" / "fair-rental-days.yaml"),
           "worktree": "/"}
    assert d.route("POST", "/runs", bad)[0] == 422
    bad2 = {"csrf": d.csrf, "kind": "eval", "suite": "/etc/passwd", "worktree": "demo/fair_rental_days/repo"}
    assert d.route("POST", "/runs", bad2)[0] == 422
    assert d.route("POST", "/runs", {"csrf": d.csrf, "kind": "rm -rf"})[0] == 422


def test_eval_run_end_to_end():
    d = Dashboard(REPO)
    ok = {"csrf": d.csrf, "kind": "eval", "suite": str(DEMO / "suites" / "fair-rental-days.yaml"),
          "worktree": "demo/fair_rental_days/repo"}
    code, _, body = d.route("POST", "/runs", ok)
    assert code == 200 and "FAILED" in body  # baseline is buggy by design


def test_finding_store_roundtrip_and_gate(tmp_path):
    st = FindingStore(tmp_path)
    f = group_reviews("F-1", "t", "s", ["tr"], repro=["r"], expected="e", actual="a",
                      hypothesis="h", confidence=0.9, eval_criteria="c")
    st.save(f)
    assert [x.id for x in st.list()] == ["F-1"]
    assert st.approve("F-1").status == "approved"
    low = group_reviews("F-2", "t", "s", ["tr"], repro=["r"], expected="e", actual="a",
                        hypothesis="h", confidence=0.1, eval_criteria="c")
    st.save(low)
    from harness.feedback.findings import FindingError
    with pytest.raises(FindingError):
        st.approve("F-2")


class TestLiveHTTP:
    @pytest.fixture()
    def server(self, dash):
        Handler.dashboard = dash
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        yield srv, dash
        srv.shutdown()

    def _get(self, server, path):
        srv, _ = server
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}{path}") as r:
            return r.status, r.read().decode()

    def _post(self, server, path, fields):
        srv, _ = server
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}{path}", data=data)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_get_overview(self, server):
        code, body = self._get(server, "/")
        assert code == 200 and "ForgeLoop" in body

    def test_post_approve_flow(self, server):
        _, dash = server
        assert self._post(server, "/findings/FIND-WEB-1/approve", {})[0] == 403
        code, body = self._post(server, "/findings/FIND-WEB-1/approve", {"csrf": dash.csrf})
        assert code == 200 and "approved" in body

    def test_put_delete_rejected(self, server):
        import urllib.error
        srv, _ = server
        for method in ("PUT", "DELETE"):
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/", method=method)
            try:
                urllib.request.urlopen(req)
                assert False, method
            except urllib.error.HTTPError as e:
                assert e.code == 405


def test_module_entrypoint_help():
    import subprocess, sys
    r = subprocess.run([sys.executable, '-m', 'harness.web', '--help'], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and '--port' in r.stdout

