# Chunked Port Strategy (Baseline)

This is a baseline approach: port AERMOD one file at a time with a 128K token cap per request.

## Strategy

1. Generate a summary of `modules.f` variables (MODULE declarations with SAVE)
2. Port each Fortran file separately, staying under 128K tokens
3. Assemble into working implementation
4. Same contract and verification as full-context port

## Module Variable Summary

First pass: Extract all MODULE variables with SAVE from modules.f:

```
=== FILE: aermod_py/module_vars_summary.md ===

# Module Variables from modules.f

## MODULE MetVars
- REAL(8) :: USTAR  ! friction velocity
- REAL(8) :: L      ! Monin-Obukhov length
...

## MODULE SourceVars
...
```

## Chunked Porting Sequence

For each Fortran file:

**Prompt**:
```
Port {filename} from Fortran to Python.

Context:
- Module variables summary (attached)
- Contract (attached)
- Previously ported files (attached if needed)

Generate Python equivalent with same structure and contract requirements.
```

**Order**:
1. modules.f → state.py, constants.py
2. meteorology files → meteorology.py
3. calc1.f, calc2.f → dispersion.py
4. prise.f → plume_rise.py
5. sigmas.f → sigmas.py
6. aermod.f (hourly loop) → core.py
7. __init__.py (glue)

## Limitations

Compared to full-context port:
- Model can't see full context, may miss cross-file dependencies
- Requires more manual coordination between files
- Module interfaces must be well-documented
- Higher chance of integration issues

## Testing

Same harness and verification as main port.

This baseline helps us compare:
- Full 1M context (Gemini 4 Argon) vs chunked approach
- One-pass vs multi-pass strategies
- End-to-end quality and repair iterations needed
