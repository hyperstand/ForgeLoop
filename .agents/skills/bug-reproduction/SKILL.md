---
name: bug-reproduction
description: Reproduce a reported failure with a minimal fixture before fixing.
---
## Procedure
1. Copy the failing input to `artifacts/repro/`. 2. Run the narrowest eval/grader.
3. Record actual vs expected + trace ID. Do not edit source until the repro fails on baseline.
