# Evaluation Design — trace, dataset, grader, regression

## Trace (schema v1, `harness/traces/schema.py`)
`trace_id, task_id, ts, provider, model, params, context_refs, tool_calls[{name,args,result,latency}],
retrieved_evidence[], intermediates[], prediction, correction, outcome, errors[], usage, code_versions`.
Redacted, append-only JSONL; review records stored separately.

## Review → finding
`ReviewRecord` compares `predicted vs corrected + evidence` → `category` (10-way) + `actionable?`.
`Finding` groups records: stable id (`FIND-<slug>-NNNN`), repro steps, expected/actual, hypothesis,
frequency/impact, confidence, counterexamples, eval criteria, `status`. Approval is explicit.

## Eval case (`harness/evals/`)
```yaml
id: fair-rental-days-001
fixture: fixtures/rental_001.json        # input (read-only)
expected: expected/rental_001.json       # expected output (read-only, SHA-pinned)
method: exact                             # exact | tolerance | script | model_graded
pass_criteria: "fair_rental_days == 5"
category: mapping_error
dataset_version: v1
```
- `exact`: JSON equality on selected fields. `tolerance`: numeric `|actual-expected| <= tol`.
  `script`: repo-local grader `graders/<name>.py` exit 0. `model_graded`: calibrated + human spot-check only.
- Numeric/structured tasks prefer exact/tolerance over similarity.

## Runner
`Runner.run(suite, worktree)` verifies fixture SHAs → executes grader per case → writes
`artifacts/eval_report.json` + `.md`. `compare(baseline_report, candidate_report)` lists
`fixed[], regressed[], unchanged[]`; any regression fails acceptance even if the target passes.
Dataset + grader versions recorded in every report.

## Regression policy
Targeted suite proves the fix; regression suite (`rental-income-regression.yaml`) guards neighbors.
A change is accepted only on targeted-pass AND zero-regressions AND human APPROVED.
