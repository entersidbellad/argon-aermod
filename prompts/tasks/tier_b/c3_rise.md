Chunk 3 of 5. Write the new module `aermod_py/prime_rise.py`, complete:
NUMRISE and WAKE_DBG (prime.f) and PRMDELH (prise.f), following the plan's
conventions. NUMRISE writes most of the PRIME debug values listed under
`## PRIME.DBG` (sub `NUMRISE`); emit them in AERMOD's order, one row per WRITE
(one per step when written inside the step loop). Call the functions in
`prime_base.py` and `prime_wake.py` and use `PrimeState` exactly as their
current code (shown) defines them; do not redefine them. PRMDELH reads and sets
MAIN1 variables on `state` (upper case) as the tier A plume-rise code does.

If these units need SAVEd locals or PrimeState fields that `prime_state.py`
lacks, also return `prime_state.py` complete with only those fields added.
Otherwise return only `prime_rise.py`. Do not change any other file.
