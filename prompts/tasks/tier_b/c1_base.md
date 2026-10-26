Chunk 1 of 5. Write two new modules, complete:

1. `aermod_py/prime_state.py`: the `PrimeState` dataclass and the PARAMETER
   constants for MODULE PRIME_PARAMS, PRIME_NUMPARM, PRIME_DFSN, PRIME_WAKEDAT,
   PRIME_AMBIENT, PRIME_PLU and PRM2_WAKEDAT (modules.f lines shown), every
   variable with its Fortran default (0.0 / 0 / False, arrays zero-filled with
   the declared length). Add a field for every SAVEd local of the prime.f units
   you port in this chunk, named `<unit>_<var>`. Later chunks may need more
   SAVEd locals; give the class a short note saying they add fields with the
   same naming rule (they will rewrite this file only if needed).
2. `aermod_py/prime_base.py`: PRIME1, NUMPR1, WAKE_INI, WAKE_SCALES, WAKE_DIM,
   POSITION, CAVITY_HT, SZSFCLPR, SIGYPR, SIGZPR, WAKE_XSIG, FNERF, FNERFC,
   ERFDIF, FRGAUSS, NUMGRAD, WAKE_DRDX, WAKE_XA, WAKE_XA2, WAKE_CAV0, ZMET,
   ZSTREAM, RATE, LUMP, MARCHING, UNLUMP, following the plan's conventions.
   WAKE_INI is called from PCALC with MAIN1 values as arguments; keep its
   Fortran argument list.

Do not change any existing file; nothing calls these modules yet. Both
modules must import cleanly on their own. Return only these two files.
