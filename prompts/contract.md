# AERMOD Python port: contract

You are translating the in-scope physics of EPA AERMOD 26135 from Fortran to a
Python package, `aermod_py`. AERMOD's SETUP phase (runstream parsing) and its
output writers are **not** ported: `harness/glue.py`, included below, does that
work and hands your code the values SETUP would have left in the module
variables. Everything from `SUBROUTINE HRLOOP` down is yours.

Scope: POINT sources, FLAT terrain, rural, concentration only, 1-hour averages.
Tier A cases have no building data; tier B cases add PRIME downwash. Any deck
outside this scope is rejected by `glue.load_project` before your code runs.

## Entry point

`aermod_py/__init__.py` must export:

```python
def run_case(project: glue.Project, met: glue.Met, setup: dict, *,
             debug: bool = False) -> glue.Result:
```

Import the glue types with `import glue` (the harness puts `harness/` on
`sys.path`). The function must not read or write files, print, or keep state
between calls.

`glue.Result` has three fields:

- `dates`: int64 array, the KURDAT (YYMMDDHH, 2-digit year) of every hour HRLOOP
  processes, in order. It must equal `glue.expected_dates(project, met)`, which
  is every surface record inside the STARTEND window (ISDATE..IEDATE).
- `conc`: float64 array of shape `(len(dates), NUMREC)`. Row h, column IREC-1
  is the 1-hour average AERMOD writes to the POSTFILE for hour h and receptor
  IREC, in ug/m^3, for the POSTFILE source group: the sum over the group's
  sources (`IGROUP(ISRC, IGRP) == 1`) of HRVAL. Do not round; the harness
  writes the POSTFILE.
- `debug`: list of tuples, empty unless `debug=True` (see "Debug rows").

## Inputs

**`setup: dict`** holds every module variable the in-scope Fortran reads but
never assigns. Its keys are exactly the names in `harness/setup_inputs.json`
(the Fortran names, upper case). Values follow the Fortran declaration:

| Fortran | Python |
|---|---|
| DOUBLE PRECISION scalar | `float` |
| INTEGER scalar | `int` |
| LOGICAL scalar | `bool` |
| CHARACTER scalar | `str` (trailing blanks stripped) |
| array | `numpy.ndarray` with the Fortran shape: `A(I,J)` is `a[I-1, J-1]` |
| CHARACTER array | object array of `str` |
| unallocated ALLOCATABLE | `None` (never indexed by in-scope code) |

These values are checked bit for bit against an instrumented AERMOD that dumps
the module variables just before `CALL HRLOOP`. Values set by a DATA statement
or PARAMETER (for example `GRIDHT`) and every variable the in-scope code
assigns itself are not in `setup`; take them from the Fortran.

**`project: glue.Project`** is the parsed deck. You need little of it beyond
`setup`; it is there for `ISDATE`/`IEDATE`, the receptor count, and to pass to
`glue.expected_dates`.

**`met: glue.Met`** replaces METEXT's file reads:

- `met.surface[NAME][h]` is the value the list-directed
  `READ(MFUNIT, *) IYEAR, IMONTH, ..., NCLOUD` assigns for surface record h
  (0-based, counting every data record in the file, including those outside
  STARTEND). Names are the READ list in `glue.SURFACE_READ`.
- `met.profile[NAME][j]` is the value of `READ(IPROFN, *) KYEAR, ..., PFLSW`
  for profile row j. Hour h's levels are rows
  `met.profile_start[h]:met.profile_start[h+1]`, in file order.
- `met.sfc_headers` holds the header line(s) (lines containing a colon).

Translate each READ of a data record into taking the next record from these
arrays, and each BACKSPACE into stepping back. METEXT's `READ(...,'(A256)')
BUFFER` reads only feed messages and header checks; you may drop them along
with any statement whose only effect is an ERRHDL message. ERRHDL itself is not
ported: a warning or informational call becomes nothing, a fatal ('E') call
becomes `raise RuntimeError(...)`. Keep every assignment that a later
calculation reads. The look-ahead READ under `HBPLUME`
is out of scope (`HBPLUME` is `False` in `setup`).

HRLOOP's own date handling decides which records are processed: records before
ISDATE are read and skipped, processing stops after IEDATE or at the end of the
file.

## Translation rules

1. Every Fortran DOUBLE PRECISION value is a Python `float` or numpy
   `float64`. Nothing in scope is single precision.
2. Keep constants exactly as written, including `D0` literals, and keep the
   order of operations where floating-point results could differ: `A*B/C` is
   not `A*(B/C)`.
3. Keep branch order and loop structure. Nested IFs stay nested; GOTOs become
   loops with `break`/`continue` or flags. Don't merge or simplify branches.
4. Fortran intrinsics map to `math` (scalars) or numpy (arrays): `DSQRT` is
   `sqrt`, `DLOG` is `log`, `DLOG10` is `log10`, `NINT` rounds half away from
   zero (not Python's `round`), `INT` truncates toward zero, `MOD` takes the sign of
   the first argument (`math.fmod` for reals; not Python's `%`), `SIGN(A,B)` is `math.copysign(abs(A), B)`.
   Integer division truncates toward zero.
5. Comment every 1-based to 0-based index change, for example
   `# Fortran ISRC=1..NUMSRC -> isrc in range(NUMSRC)`.
6. MODULE variables and SAVEd locals become fields of explicit dataclasses
   passed between functions. No module-level mutable state.
7. Every function's docstring names the Fortran unit it comes from, for example
   `"""SUBROUTINE PCALC (calc1.f)."""`.
8. The hour loop is explicit. Within an hour you may vectorise over receptors
   with `import numpy as xp` (so the port can later run on JAX), provided the
   arithmetic per receptor is the same as the Fortran's.

## Debug rows

With `debug=True`, emit the values AERMOD prints under
`CO DEBUGOPT MODEL METEOR PRIME`, as tuples

    (KURDAT, ISRC, IREC, comp, sub, var, value)

in the order AERMOD computes them. The allowed `(sub, comp, var)` triples are
listed in `prompts/debug_vars.md`, which is generated from real AERTEST
debug files written by our compiled AERMOD. Use only those names. For
example: `METDEB` `USTAR`, `WSTAR`, `ZI`, `OBULEN`, `UEFF`; `PCALC` `DHCRIT`,
`XFINAL`, `DHFAER`; `IBLVAL`/`PAN` `UEFF`; `DELTAH`/`PLM` `DHP`; `AER_PCHI`/`PAN`
`AEROUT`; `PCALC`/`PRIME` `HRVAL`.

- `KURDAT`: the hour, YYMMDDHH with a 2-digit year (as in `Result.dates`).
- `ISRC`: 1-based source index; 0 for METDEB rows.
- `IREC`: 1-based receptor index for rows printed per receptor, 0 for rows
  printed once per hour or once per source-hour. For METDEB `GRID*` rows it is
  the 1-based grid level.
- `comp`: `"PAN"` inside the meander/pancake pass, `"PLM"` inside the coherent
  plume pass, `"PRIME"` for PRIME, `""` otherwise. The `level` column of
  `debug_vars.md` says which kind of key each name takes.
- `sub`: the Fortran subroutine whose WRITE prints the value.
- `var`: the name in `debug_vars.md`. Names with a dot (`GAUSSIAN.SY`) are a
  column of a DEBOUT table row; names with an operator are the printed
  expression.
- If AERMOD prints the same `(KURDAT, ISRC, IREC, comp, sub, var)` more than once
  (iterations in DELTAH, NUMRISE, ...), emit one row per print in the same order.

`harness/debugdiff.py` compares these rows with the parsed reference: the first
value that differs by more than one unit in AERMOD's last printed digit, or the
first row you didn't emit, is what the repair loop works on.

## How the port is judged

`harness/run_port.py` checks `Result` (dates, shape, dtype, finite values) and
writes the POSTFILE. `harness/compare.py` then scores it on every case:

- **EPA rule**: against EPA's reference POSTFILE (our binary's, for the two
  cases EPA ships none), each of the three "best-fit slope" figures EPA's kit
  uses (through-origin least squares, the R script's `lm` line, and the ratio
  of mean concentrations) must be within 1 ± 0.001.
- **Strict rule** against our compiled binary: every (hour, receptor) row
  present; zero/nonzero agreement ≥ 99.9%; p99 relative error ≤ 1e-4 on values
  ≥ 1% of the case maximum; every receptor's H4H (4th-highest daily maximum)
  design value within 1e-4 relative.

One case is held out and never shown to the repair loop.

## Output format

Emit each file of the package with a marker line, and nothing else outside
file contents:

```
=== FILE: aermod_py/__init__.py ===
<contents>
=== FILE: aermod_py/hrloop.py ===
<contents>
```

Only `.py` files under `aermod_py/` are accepted. Markdown fences around
contents are stripped.
