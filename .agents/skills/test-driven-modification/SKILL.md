---
name: test-driven-modification
description: Make scoped edits only inside allowlisted paths, then run checks.
---
## Procedure
1. `read_file` target. 2. `edit_file` with exact old_string. 3. `lint` + `run_tests`.
4. Never touch `evidence/` or expected outputs. Failed validation blocks approval.
