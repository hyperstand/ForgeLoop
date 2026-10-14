"""ForgeLoop local dashboard views (stdlib only, all output html-escaped)."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List

CSS = ("body{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;padding:0 1em}"
       "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}"
       ".pass{color:green}.fail{color:red}nav a{margin-right:1em}pre{background:#f6f6f6;padding:1em;overflow:auto}")


def layout(title: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body>"
            f"<nav><a href='/'>tasks</a><a href='/evals'>evals</a><a href='/findings'>findings</a>"
            f"<a href='/ledger'>ledger</a></nav><h1>{html.escape(title)}</h1>{body}</body></html>")


def _row(cells: List[str]) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def overview(tasks: List[Dict[str, Any]], ledger: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
    body = (f"<h2>Run ledger</h2><p>{html.escape(str(ledger.get('runs', 0)))} runs, "
            f"${html.escape(str(ledger.get('total_cost_usd', 0)))}, "
            f"{html.escape(str(ledger.get('total_latency_s', 0)))}s</p>"
            f"<h2>Tasks</h2><table><tr><th>id</th><th>state</th><th>updated</th></tr>"
            + "".join(_row([f"<a href='/tasks/{html.escape(t['id'])}'>{html.escape(t['id'])}</a>",
                            html.escape(t['state']), html.escape(t.get('updated', ''))]) for t in tasks)
            + "</table><h2>Candidates</h2><table><tr><th>id</th><th>targeted</th><th>regression</th></tr>"
            + "".join(_row([html.escape(c['id']), html.escape(c.get('targeted', '?')),
                            html.escape(c.get('regression', '?'))]) for c in candidates)
            + "</table>")
    return layout("ForgeLoop dashboard", body)


def task_detail(task: Dict[str, Any], reviewable: bool, csrf: str) -> str:
    rows = ""
    for e in task.get('events', []):
        rows += _row([html.escape(str(e.get('ev', ''))),
                      html.escape(str(e.get('tool', e.get('state', '')))),
                      html.escape(str(e.get('ts', '')))])
    form = (f"<form method=post action='/tasks/{html.escape(task['id'])}'>"
            f"<input type=hidden name=csrf value='{html.escape(csrf)}'>"
            f"<button disabled>transitions via CLI only</button></form>" if reviewable else "")
    return layout(f"task {task['id']}",
                  f"<p>state: <b>{html.escape(task['state'])}</b></p>"
                  f"<p>{html.escape(task.get('description', ''))}</p>"
                  f"<h2>history</h2><table><tr><th>event</th><th>detail</th><th>ts</th></tr>{rows}</table>{form}")


def evals_page(suites: List[str], reports: List[Dict[str, Any]], csrf: str) -> str:
    opts = "".join(f"<option>{html.escape(s)}</option>" for s in suites)
    reps = "".join(_row([html.escape(r.get('suite', '')), html.escape(str(r.get('passed', ''))),
                         html.escape(str(r.get('failed', '')))]) for r in reports)
    return layout("evaluations",
                  f"<h2>Run a suite</h2><form method=post action='/runs'>"
                  f"<input type=hidden name=csrf value='{html.escape(csrf)}'>"
                  f"<input type=hidden name=kind value='eval'>"
                  f"<select name=suite>{opts}</select>"
                  f"<input name=worktree placeholder='candidates/&lt;id&gt;/repo or demo/...'>"
                  f"<button>run eval</button></form>"
                  f"<form method=post action='/runs'><input type=hidden name=csrf value='{html.escape(csrf)}'>"
                  f"<input type=hidden name=kind value='demo'><button>run fair_rental_days demo</button></form>"
                  f"<h2>Latest reports</h2><table><tr><th>suite</th><th>passed</th><th>failed</th></tr>{reps}</table>")


def findings_page(findings: List[Dict[str, Any]], csrf: str) -> str:
    rows = ""
    for f in findings:
        btn = (f"<form method=post action='/findings/{html.escape(f['id'])}/approve'>"
               f"<input type=hidden name=csrf value='{html.escape(csrf)}'><button>approve</button></form>"
               if f.get('status') == 'draft' else "")
        rows += _row([html.escape(f['id']), html.escape(f.get('title', '')), html.escape(f.get('status', '')),
                      html.escape(f.get('subsystem', '')), btn])
    return layout("findings",
                  f"<table><tr><th>id</th><th>title</th><th>status</th><th>subsystem</th><th></th></tr>{rows}</table>")


def trace_page(trace_id: str, trace: Dict[str, Any]) -> str:
    return layout(f"trace {trace_id}", f"<pre>{html.escape(json.dumps(trace, indent=2)[:20000])}</pre>")


def ledger_page(rows: List[Dict[str, Any]]) -> str:
    body = ("<table><tr><th>ts</th><th>kind</th><th>provider</th><th>model</th>"
            "<th>latency</th><th>cost</th></tr>"
            + "".join(_row([html.escape(str(r.get('ts', ''))), html.escape(r.get('kind', '')),
                            html.escape(r.get('provider', '')), html.escape(r.get('model', '')),
                            html.escape(str(r.get('latency_s', ''))), html.escape(str(r.get('cost_usd', '')))])
                       for r in rows[-100:]) + "</table>")
    return layout("run ledger", body)


def result_page(title: str, ok: bool, detail: str) -> str:
    cls = "pass" if ok else "fail"
    return layout(title, f"<p class={cls}>{html.escape('OK' if ok else 'FAILED')}</p><pre>{html.escape(detail[:20000])}</pre>")
