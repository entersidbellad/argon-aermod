# Repair one divergence in the AERMOD Python port

You wrote `aermod_py`, a Python translation of AERMOD 26135's physics, under
the contract in `prompts/contract.md`. The repair loop ran it on a test case and
found where it first leaves AERMOD. The input gives you:

- the case and hour, and the first problem in AERMOD's order: either the
  first debug value that differs from AERMOD by more than one unit in AERMOD's
  last printed digit (names as in `prompts/debug_vars.md`: Fortran subroutine,
  pass `PAN`/`PLM`/`PRIME`, variable, source and receptor index), the first
  debug row the port failed to emit, or the traceback if the port crashed;
- the met values for that hour;
- the Fortran source of the unit that printed the value;
- the current Python files that translate that unit.

Find the single most likely cause and fix it with a minimal patch. Every value
AERMOD printed before this one matched, so the error is most likely in the
computation between the last matching value and this one, in the unit shown.
(Not every intermediate is printed, so it can also sit in a unit that unit
calls.)

Rules:

- Change at most two files, and only what the fix needs. Keep the contract's
  translation rules (float64, constants and operation order as in the
  Fortran, docstrings naming the Fortran unit, no module-level state).
- Return each changed file complete, not as a diff.
- Do not add special cases for the test case, hour or receptor.

The patch is kept only if no case that passed before fails afterwards and
this case's first problem moves later in AERMOD's order (or disappears).

Respond in exactly this format:

```
=== HYPOTHESIS ===
<one or two sentences: what is wrong and why>
=== FILE: aermod_py/<name>.py ===
<complete file>
```
