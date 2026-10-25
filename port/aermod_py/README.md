# port/aermod_py

**Every Python file here is written by Gemini 4 Argon. Do not hand-edit.**

Files arrive only through `split.py`, called by `agent/port.py`, `agent/repair_loop.py` or the chunked baseline. Each write is recorded in `files.json` beside the saved reply under `agent/runs/`. `python split.py --verify`, which also runs in the tests and CI, fails if any file here is not byte-identical to what a completed, recorded Argon interaction split into. This README is the only human-owned file.

## Contract (full text: `prompts/contract.md`)

```python
run_case(project: glue.Project, met: glue.Met, setup: dict, *, debug=False) -> glue.Result
```

- `Result(dates, conc[hour, receptor], debug)`: float64 and finite. The dates must equal `glue.expected_dates`.
- `debug=True` returns `(KURDAT, ISRC, IREC, COMP, SUB, VAR, value)` rows named after AERMOD's DEBUGOPT output (`prompts/debug_vars.md`).
- Translation rules:
  - float64 for DOUBLE PRECISION;
  - a comment at every 1-to-0-based index change;
  - module and SAVE state as dataclasses;
  - each function's docstring names its Fortran unit;
  - `import numpy as xp`.

Scope, cases and the pass rules are in the top-level `README.md`. The pass rules are implemented in `harness/compare.py`.
