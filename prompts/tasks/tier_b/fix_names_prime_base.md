Fix MAIN1 attribute names in `aermod_py/prime_base.py`.

`AermodState` (tier A `state.py`) keeps MAIN1 variables under their exact
Fortran/setup spelling, which is mixed case for some logical options. The plan
said "upper case" and that was wrong for these names: `prime_base.py` reads
attributes that do not exist on `AermodState`, so it raises AttributeError the
first time they are reached. Rename each one to the existing attribute:

- `state.L_ORD_TURB` -> `state.L_ORD_Turb` (lines 24)

Change nothing else: every other line must stay byte-identical. Return
`prime_base.py` complete.
