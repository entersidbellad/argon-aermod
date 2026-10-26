# Tier B plan: porting PRIME building downwash in chunks

The tier A port (shown through its API index below) has no building downwash.
Tier B adds AERMOD's PRIME algorithm. Because the PRIME Fortran is large, it is
ported in five requests, leaves of the call graph first, so every request can
see the exact signatures of what it calls. This request is one of them; the
TASK at the end says which units to write.

## Module layout (fixed for all chunks)

| Python module | Fortran |
|---|---|
| `prime_state.py` | `MODULE PRIME_PARAMS, PRIME_NUMPARM, PRIME_DFSN, PRIME_WAKEDAT, PRIME_AMBIENT, PRIME_PLU, PRM2_WAKEDAT` (modules.f) as one dataclass `PrimeState`, plus the PARAMETERs as module-level constants (`MXNW`, `MXENT`, `MXENTP1`, `MXNTR`, `MXNZ`, `MXNZP1`, `P2MXNTR`, `IO5`, `IO6`) |
| `prime_base.py` | PRIME1, NUMPR1, WAKE_INI, WAKE_SCALES, WAKE_DIM, POSITION, CAVITY_HT, SZSFCLPR, SIGYPR, SIGZPR, WAKE_XSIG, FNERF, FNERFC, ERFDIF, FRGAUSS, NUMGRAD, WAKE_DRDX, WAKE_XA, WAKE_XA2, WAKE_CAV0, ZMET, ZSTREAM, RATE, LUMP, MARCHING, UNLUMP (prime.f) |
| `prime_wake.py` | WAKE_U_TURB, WAKE_TURB, WAKE_U, WAKE_SIG, WAKE_DFSN, WAKE_DFSN2, WAKE_FQC, CAV_SRC (prime.f) |
| `prime_rise.py` | NUMRISE, WAKE_DBG (prime.f), PRMDELH (prise.f) |
| `prmcalc.py` | PRMCALC, GAMCALC, PRMHEFF, PRM_PCHI, PRM_PLUME (calc1.f); then PCALC in `calc1.py` and `run_case` in `__init__.py` are wired to them |

## Conventions (every chunk must follow them exactly)

- **State.** PRIME module variables live in `PrimeState` (all names lower
  case, arrays as float64 numpy arrays with the Fortran length, Fortran element
  `a(i)` is `a[i-1]`). The running `AermodState` carries it as `state.prime`;
  `run_case` creates `state.prime = PrimeState()` right after
  `AermodState.from_setup` and then calls `numpr1(state)` and `prime1(state)`,
  as AERMOD's main program does before HRLOOP. MAIN1 variables stay on `state`
  (upper-case names, as in the tier A port). A SAVEd local of a PRIME unit
  becomes a `PrimeState` field named `<unit>_<var>`, e.g. `numrise_xxx`.
- **Functions.** Fortran unit `NAME` becomes `name(state, ...)` (lower case;
  `state` is the `AermodState`, always first, even if unused). The remaining
  parameters are the Fortran dummy arguments the unit reads, in Fortran
  argument order, with Fortran names in lower case. Dummy arguments the unit
  assigns are returned: one value directly, several as a tuple in Fortran
  argument order. An argument that is both read and assigned is a parameter and
  also returned. An array argument the unit fills in place may be passed in and
  mutated instead; say so in the docstring. A FUNCTION returns its value.
  The docstring's first line names the unit (`"""SUBROUTINE WAKE_DIM (prime.f)."""`)
  and the docstring lists what is returned, e.g. `Returns (wz, wy)`.
- **Arithmetic.** float64 throughout; keep the Fortran constants, operation
  order, branch order and loop structure (the contract's translation rules).
  Fortran `DO`-loop indices stay 1-based in comments; comment every index shift.
- **Debug.** When `state.PRIMEDBG` is set (the tier A `from_setup` sets it for
  debug runs with building data), emit the values AERMOD writes to the PRIME
  debug file with `state.emit_debug(...)`, comp `"PRIME"`, using only the
  `(sub, var)` names listed under `## PRIME.DBG` in `debug_vars.md`, in the order
  AERMOD writes them. Values that AERMOD only writes as text, and every other
  WRITE, are dropped. ERRHDL calls follow the contract (fatal -> RuntimeError).
- **Imports.** `prime_state` imports nothing from the package except `state`
  helpers. `prime_base` may import `prime_state`, `state`, and tier A modules
  (`iblval.locate`, `metext.gintrp`, ...). `prime_wake` may also import
  `prime_base`; `prime_rise` also `prime_wake`; `prmcalc` also `prime_rise`. Never
  import a later module from an earlier one. No import cycles.
