Relabel the trajectory debug emits after `wake_dfsn2` in `aermod_py/prime_rise.py`.

In `numrise`, the `if ldb:` block that follows the call
`wake_dfsn2(state, ldb, xbi, szi, syi, xtr, ztr, ntr, dbgunt)` (lines 430-436)
emits XTR, YTR, ZTR and RTR with sub name `"NUMRISE"`. In prime.f these values
are written under the header "Trajectory arrays after CALL WAKE_DFSN2", and the
debug-variable contract (`prompts/debug_vars.md`) lists them under sub
`WAKE_DFSN2`. Change the first string argument of exactly these four calls:

- line 433: `p.emit_debug(state, "NUMRISE", "XTR", ...)` -> `"WAKE_DFSN2"`
- line 434: `p.emit_debug(state, "NUMRISE", "YTR", ...)` -> `"WAKE_DFSN2"`
- line 435: `p.emit_debug(state, "NUMRISE", "ZTR", ...)` -> `"WAKE_DFSN2"`
- line 436: `p.emit_debug(state, "NUMRISE", "RTR", ...)` -> `"WAKE_DFSN2"`

Do NOT change the identical-looking block before the `wake_dfsn2` call
(lines 417-420); it stays `"NUMRISE"`. Change nothing else: every other line
must stay byte-identical. Return `prime_rise.py` complete.
