Fix MAIN1 attribute names in `aermod_py/prime_wake.py`.

`AermodState` (tier A `state.py`) keeps MAIN1 variables under their exact
Fortran/setup spelling, which is mixed case for some logical options. The plan
said "upper case" and that was wrong for these names: `prime_wake.py` reads
attributes that do not exist on `AermodState`, so it raises AttributeError the
first time they are reached. Rename each one to the existing attribute:

- `state.L_AWMA_UTURB` -> `state.L_AWMA_UTurb` (lines 326, 366)
- `state.L_AWMA_UTURBHX` -> `state.L_AWMA_UTurbHX` (lines 186, 301, 326, 338, 366)
- `state.L_ORD_CAV` -> `state.L_ORD_Cav` (lines 1101, 1274)

Change nothing else: every other line must stay byte-identical. Return
`prime_wake.py` complete.
