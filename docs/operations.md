# ForgeLoop — Operations — install, configure, run

## Install
```powershell
git clone <repo>; cd llm_new
python -m pip install -r requirements.txt   # pyyaml, pytest
```

## Configure providers (`examples/models.yaml`)
```yaml
default: mock
providers:
  mock: { kind: mock }
  openai_compat:
    kind: openai_compat
    base_url: "${OPENAI_BASE_URL:-https://api.openai.com/v1}"
    model: "${HARNESS_MODEL:-gpt-4o-mini}"
    api_key_env: OPENAI_API_KEY
    timeout_s: 60
  anthropic:
    kind: anthropic
    base_url: "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
    model: "${HARNESS_ANTHROPIC_MODEL:-claude-sonnet-4-5}"
    api_key_env: ANTHROPIC_API_KEY
    timeout_s: 60
```
No keys → live tests skip; mock runs offline. `HARNESS_MODEL` overrides model without code changes.
`python -m harness.cli task-run` resolves `--provider` through this file (`harness/providers/factory.py`),
so switching models never requires orchestrator rewrites.

## Run
```powershell
pytest -q                       # offline suite (must be green)
python demo/run_demo.py         # end-to-end fair_rental_days loop
python -m harness.cli --help    # task run / eval run /Finding approve
python -m harness.cli task-run --task candidates/FIND-RENTAL-0042/task.yaml --provider mock
python -m harness.cli eval-run --suite evals/suites/fair-rental-days.yaml --worktree candidates/FIND-RENTAL-0042/repo
python -m harness.cli compare --baseline artifacts/baseline_report.json --candidate artifacts/eval_report.json
```

Run every command with `--provider anthropic` instead of `mock` once `ANTHROPIC_API_KEY` is set;
without keys the Anthropic adapter raises `missing_creds` and live tests skip.

## Observability
`task-run` and `eval-run` append cost/latency records to `.harness/ledger.jsonl`
(`harness/observe/ledger.py`; per-1k-token rates, mock is free). Model comparisons
(`harness/evals/model_compare.py`: same suite, multiple providers, one table with
provider/model/params/tool-compat/cost) are recorded as `comparison` entries.

## Dashboard (stdlib only, localhost)
```powershell
python -m harness.cli serve --port 8080   # or: python -m harness.web --port 8080
```
Pages: overview (tasks, ledger, candidates), task detail, evals (run form), findings
(approve button), redacted trace view, ledger. Exactly two actions exist:
`POST /findings/<id>/approve` (same gate as `Finding.approve()`) and `POST /runs`
(`kind=eval` on allowlisted suites/worktrees, or `kind=demo`). All POSTs need the
per-process CSRF token, bind is refused outside localhost, and actions are audit-logged.

## Layout notes
Task env: `candidates/<id>/{task.yaml,EXEC_PLAN.md,RESULTS.md,repo/,evidence/,evals/,artifacts/}`.
`repo/` writable; `evidence/` + `evals/expected` read-only + SHA-pinned.
