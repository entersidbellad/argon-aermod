# Port AERMOD to Python

You are porting EPA's AERMOD air dispersion model from Fortran to Python in a single pass.

## Context

Below you will find:
1. A subroutine index for navigation
2. The complete Fortran source code for the in-scope physics

Your task: Generate a complete, working Python implementation that matches the Fortran behavior exactly.

## Contract

Read `contract.md` for the complete interface specification. Key points:

- Entry point: `run_case(project, met, sources=None, debug=False) -> Result`
- Vectorized over receptors, explicit hour loop
- Float64 for DOUBLE PRECISION
- Comment every 1-to-0-based index change
- Preserve constants, branch order, algorithm structure verbatim
- Each function docstring names its Fortran subroutine source
- Debug mode returns intermediates matching DEBUGOPT variable names
- Use `import numpy as xp` for future JAX compatibility

## Scope

**Physics**: Point sources, flat terrain, rural, concentration only, 1-hour averages

**Tier A** (this port): No building downwash  
**Tier B** (if PRIME is included): Add building downwash

## Input Parsing

Do NOT port AERMOD's input parsing or output formatting. Use pyaermod:

```python
from pyaermod import input_reader
from pyaermod.met_readers import read_surface_file, read_profile_file

# Project and sources come from pyaermod.input_reader.parse_inp()
# Met data from pyaermod.met_readers
```

Your port handles only the physics: met interpolation → concentration calculation.

## Output Format

Structure your output with file markers:

```
=== FILE: aermod_py/__init__.py ===
<content>

=== FILE: aermod_py/core.py ===
<content>

=== FILE: aermod_py/meteorology.py ===
<content>
```

Suggested structure:
- `__init__.py`: exports run_case
- `core.py`: main run_case function, hourly loop
- `meteorology.py`: METEXT, IBLVAL, SIGGRID, TEMPGRID, WINDGRID
- `plume_rise.py`: PRISE
- `dispersion.py`: PCALC, sigma calculations
- `sigmas.py`: sigma_y, sigma_z formulas
- `state.py`: dataclasses for module/SAVE state
- `constants.py`: physical constants

## Verification Strategy

Your port will be tested against EPA test cases:
- AERTEST (hero case with building downwash)
- CAPPED_STACK2, HRDOW_STACK1, FLATELEV_FLAT_STK
- Must pass strict numerical criteria (see contract.md)

A repair loop will fix discrepancies by:
1. Running reference vs port with debug=True
2. Finding first divergent variable (debugdiff.py)
3. Generating targeted patches with the divergent subroutine's Fortran
4. Verifying no regressions

Write code that is correct the first time. Pay special attention to:
- Array index conversions (Fortran 1-based → Python 0-based)
- Loop bounds (DO I=1,N → range(N) not range(N+1))
- Array slicing (A(I:J) in Fortran is inclusive of J)
- Logical operators (Fortran .AND. → Python `and`)
- Exponentiation (Fortran ** → Python **)
- Intrinsic functions (SQRT, EXP, LOG, SIN, COS → xp.sqrt, etc.)

## DEBUGOPT Variables

Run with `CO DEBUGOPT MODEL METEOR PRIME` to see intermediate variable names.

You MUST inspect actual DEBUGOPT output to get the exact variable names.

When debug=True, return these variables in the `intermediates` dict with names exactly as printed.

## Ready?

The Fortran source follows below. Generate the complete Python port.
