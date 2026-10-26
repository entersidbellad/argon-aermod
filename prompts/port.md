# Port AERMOD to Python in one pass

You are translating the in-scope physics of EPA AERMOD 26135 (Fortran) into a
complete Python package, `aermod_py`, in a single response.

The input that follows has five parts:

1. **Contract** (`prompts/contract.md`): the entry point, what each input
   holds, the translation rules, the debug rows, and how the port is judged.
   It is binding.
2. **`harness/glue.py`**: human-written code that replaces AERMOD's SETUP
   phase and its output writers. Import it (`import glue`). Don't copy or
   re-implement it, and don't port SETUP.
3. **SETUP inputs**: every module variable your code reads but never assigns,
   with its Fortran type and rank. `run_case` receives all of them in `setup`.
4. **DEBUGOPT variables**: the only names allowed in debug rows, generated
   from real AERMOD debug output.
5. **Fortran**: a subroutine index, then the source of every program unit
   reachable from HRLOOP in this tier's scope, with `modules.f` in full.
   Calls to units whose source is not in the pack (ERRHDL, averaging, output)
   are out of scope: an ERRHDL call becomes nothing for warnings and
   informational messages, and `raise RuntimeError(...)` for fatal ('E') errors.

Work through HRLOOP in call order and translate every reachable unit. Keep the
Fortran's structure, constants and order of operations. Correctness on the
first run matters more than brevity. Watch especially for:

- 1-based to 0-based indexing (`DO I=1,N` is `range(N)`; `A(I:J)` includes J);
- integer vs real arithmetic (`NINT`, `INT`, `MOD`, integer division);
- which variable a SAVEd or MODULE value carries from one call or hour to the
  next;
- branches that depend on stability (`UNSTAB`/`STABLE`), plume state
  (`PPF`, `HSP`, penetration) or PRIME (`WAKE`) flags.

Respond with the package only: a sequence of
`=== FILE: aermod_py/<name>.py ===` blocks, starting with `__init__.py`. Put no
prose between files. Any `.py` layout under `aermod_py/` is fine; prefer one
module per Fortran file (`hrloop.py`, `metext.py`, `iblval.py`, `calc1.py`,
`calc2.py`, `prise.py`, `sigmas.py`, `prime.py`, ...) plus `state.py` for the
module-variable dataclasses.
