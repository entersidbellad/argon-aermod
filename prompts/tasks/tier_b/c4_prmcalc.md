Chunk 4 of 5. Write the new module `aermod_py/prmcalc.py`, complete: PRMCALC,
GAMCALC, PRMHEFF, PRM_PCHI and PRM_PLUME (calc1.f), following the plan's
conventions. These read and set MAIN1 variables on `state` (upper case) as the
tier A calc1/calc2 code does; call the existing tier A functions (API index)
for ANYAVG, LOCATE, GINTRP, FYPLM, DECAY, DEBOUT, VRTSBL, VRTSBN, and the
PRIME functions in `prime_base.py`, `prime_wake.py` and `prime_rise.py`, with
the signatures their code defines. PRM_PCHI's DEBOUT call and the PRIME debug
rows follow the contract and `debug_vars.md`.

`calc1.py` will import `prmcalc` in chunk 5, so `prmcalc.py` must not import
`calc1` at module level: import DEBOUT (and anything else from calc1) inside the
function that uses it, as the tier A `calc2.critds` does with `gintrp`.

Return only `prmcalc.py` (and `prime_state.py` with only added fields, if
needed). Chunk 5 wires it into PCALC.
