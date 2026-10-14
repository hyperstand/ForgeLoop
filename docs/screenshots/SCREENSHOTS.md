# What to screenshot — ForgeLoop dashboard shot list

Setup (run once before capturing):

```powershell
cd D:\llm_new
python demo/run_demo.py
python -m harness.cli serve --port 8080
```

Open `http://127.0.0.1:8080` in Edge or Chrome at 100% zoom, ~1280px window width.
Capture with `Win+Shift+S` (region) or Edge `Ctrl+Shift+S` (full page), save as PNG below.

## Required

### 1. `overview.png` — page `/`
Must show: nav bar (tasks / evals / findings / ledger), the "Run ledger" summary line,
the Tasks table (at least one task with a state), and the Candidates table with the
`FIND-RENTAL-0042` row and its targeted/regression scores.

### 2. `findings.png` — page `/findings`
Must show: the findings table with `FIND-RENTAL-0042`, its title, status, subsystem,
and (for any draft finding) the **approve** button. If no draft exists, re-run the demo
with a fresh finding or note the status shown.

## Optional

### 3. `task.png` — page `/tasks/<id>`
Pick any task id from the overview. Must show: state badge, description, and history table.
Do not use as a substitute for shots 1–2.

### 4. `eval.png` — page `/evals`
Must show: the "Run a suite" form and the latest-reports table with pass/fail counts.

## Quality rules

- PNG only, 100% browser zoom, no devtools or bookmarks bar in frame.
- Redact nothing yourself — the app already redacts secrets; if a real secret is visible, stop and report it instead of capturing.
- After saving, verify each file opens and text is readable, then commit alongside the README table that references it.
