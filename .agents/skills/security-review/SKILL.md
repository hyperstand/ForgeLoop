---
name: security-review
description: Verify jail, allowlist, and evidence protection before approving a patch.
---
## Procedure
1. Confirm all writes resolved inside `repo/`. 2. Confirm exec was allowlisted.
3. Confirm fixture SHAs unchanged. 4. Confirm no secrets in artifacts. Denylist is a backstop, not a sandbox.
