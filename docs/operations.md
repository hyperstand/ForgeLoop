# Operations — install, configure, run

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
```
No keys → live tests skip; mock runs offline. `HARNESS_MODEL` overrides model without code changes.

## Run
```powershell
pytest -q                       # offline suite (must be green)
python demo/run_demo.py         # end-to-end fair_rental_days loop
python -m harness.cli --help    # task run / eval run /Finding approve
python -m harness.cli task-run --task candidates/FIND-RENTAL-0042/task.yaml --provider mock
python -m harness.cli eval-run --suite evals/suites/fair-rental-days.yaml --worktree candidates/FIND-RENTAL-0042/repo
```

## Layout notes
Task env: `candidates/<id>/{task.yaml,EXEC_PLAN.md,RESULTS.md,repo/,evidence/,evals/,artifacts/}`.
`repo/` writable; `evidence/` + `evals/expected` read-only + SHA-pinned.
