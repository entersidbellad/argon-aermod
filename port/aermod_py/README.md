# AERMOD Python Port

**This directory is written entirely by Gemini 4 Argon. Do not hand-edit any Python code here.**

The Python implementation of AERMOD's physics is generated in a single full-context pass by Gemini 4 Argon (model ID: `gemini-4-argon`), which processes the scoped Fortran source files and produces a verified Python port.

## Generation Process

1. The Fortran source is packed into a single prompt with module index (see `../context/`)
2. Gemini 4 Argon generates all Python modules in one pass with 1M+ token context
3. The output is split by file markers into this directory structure
4. A repair loop (`../agent/repair_loop.py`) fixes discrepancies against EPA test cases
5. The port is verified against reference outputs using strict numerical criteria

## Port Contract

- Entry point: `run_case(project, met, sources=None, debug=False) -> Result`
- Returns: `Result` with `conc[hour, receptor]` in μg/m³
- Vectorized over receptors with explicit hour loop
- Float64 for DOUBLE PRECISION equivalents
- 1-to-0-based indexing changes explicitly commented
- Module/SAVE state as explicit dataclasses
- Each function docstring names its source Fortran subroutine
- `debug=True` returns intermediates matching DEBUGOPT variable names
- NumPy via `xp` namespace for future JAX compatibility

## Scope

**Tier A (No Building Downwash):**
- Point sources only
- Flat terrain
- Rural mode
- Concentration output only
- 1-hour averages
- Default physics with FLAT

**Tier B (Adds PRIME):**
- All Tier A features
- Building downwash via PRIME algorithm

## Verification

All ports must pass:
1. EPA regulatory parity (best-fit slope 1 ± 0.001)
2. Strict numerical criteria:
   - Zero/nonzero agreement ≥ 99.9%
   - P99 relative error ≤ 1e-4 on values ≥ 1% of case max
   - Per-receptor H4H design value within 1e-4

See `../harness/compare.py` for implementation details.
