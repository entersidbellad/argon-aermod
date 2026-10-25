# Edit the AERMOD Python port

You wrote `aermod_py`, a Python translation of AERMOD 26135's physics, under the
contract in `prompts/contract.md`. The input gives you the current text of some
of its files (and, when relevant, Fortran units) and a TASK describing one
change to make.

Rules:

- Make exactly the change the TASK describes and nothing else. Do not change
  numerical code, constants, operation order, names or debug output unless the
  TASK asks for it.
- Keep the contract's translation rules (float64, constants and operation order
  as in the Fortran, docstrings naming the Fortran unit, no module-level state).
- Return every new or changed file complete, not as a diff. Do not return files
  you did not change.
- Do not add special cases for any test case, hour or receptor.

Respond in exactly this format:

```
=== HYPOTHESIS ===
<one or two sentences: what you changed and why>
=== FILE: aermod_py/<name>.py ===
<complete file>
```
