Fix MAIN1 attribute names in `aermod_py/prmcalc.py`.

`AermodState` (tier A `state.py`) keeps MAIN1 variables under their exact
Fortran/setup spelling, which is mixed case for some logical options. The plan
said "upper case" and that was wrong for these names: `prmcalc.py` reads
attributes that do not exist on `AermodState`, so it raises AttributeError the
first time they are reached. Rename each one to the existing attribute:

- `state.L_AWMA_UEFF` -> `state.L_AWMA_Ueff` (lines 346)
- `state.L_AWMA_UTURB` -> `state.L_AWMA_UTurb` (lines 59, 92, 116)
- `state.L_AWMA_UTURBHX` -> `state.L_AWMA_UTurbHX` (lines 59, 87, 92, 116)
- `state.L_ORD_UEFF` -> `state.L_ORD_Ueff` (lines 328)
- `state.PRMVAL_SRC1` -> `state.PRMVAL_Src1` (lines 29, 39, 44, 49, 138, 146, 189, 207, 249)

Change nothing else: every other line must stay byte-identical. Return
`prmcalc.py` complete.
