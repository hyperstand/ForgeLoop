# Candidate task template (generated per approved finding)

`task.yaml` pins finding ID, evidence refs, allowed edit scope, forbidden paths,
acceptance criteria, and validation commands. `repo/` is the only writable tree.
`evidence/` and expected outputs are read-only + SHA-verified at eval time.
The agent may not edit `task.yaml` acceptance criteria to make its fix pass.
