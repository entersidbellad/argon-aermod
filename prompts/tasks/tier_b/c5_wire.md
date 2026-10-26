Chunk 5 of 5. Wire PRIME into the port:

1. `calc1.py`, SUBROUTINE PCALC: translate the Fortran PCALC shown in full,
   including the parts the tier A port left out because tier A had no
   building downwash: the `CALL WAKE_INI(...)` refresh when WAKE is true, the
   PRIME branch that calls `PRMCALC(XBREC, YBREC)` with the receptor's
   building-relative coordinates, GAMCALC and the GAMFACT blending of AERVAL
   and PRMVAL into HRVAL, and every debug write in those paths. Import the
   PRIME functions from `prime_base.py` and `prmcalc.py`. Do not change any
   other function in calc1.py; tier A behaviour (WAKE false) must stay
   identical.
2. `__init__.py`: in `run_case`, right after `AermodState.from_setup`, set
   `state.prime = PrimeState()` and call `numpr1(state)` and `prime1(state)`,
   as AERMOD's main program does before HRLOOP (plan, "State").

Return `calc1.py` and `__init__.py` complete, nothing else.
