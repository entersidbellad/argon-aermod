# Project status

## Verified on this branch

- **Reference build.** `ref/build.sh` builds AERMOD 26135 with gfortran from EPA's checksummed source. `ref/build_dump.sh` adds a `SETUP.DMP` writer before HRLOOP.
- **Oracles.** All 11 oracle POSTFILEs match `cases/oracle_checksums.sha256`. Ref-vs-ref passes 11/11 through `compare.py`.
- **Our binary vs EPA's files.** Identical except CAPPED_STACK1C0 (362 of 27,648 values differ) and TESTPM10 (1,243 of 1,577,664). Both still pass the EPA slope rule.
- **compare.py.** The EPA rule was checked against `Compare_AERMOD_test_cases.R` and the kit's instructions. Each criterion of both rules is tested in `tests/test_compare.py`.
- **glue.** On all 11 cases, the 253 SETUP inputs equal `SETUP.DMP` bit for bit and the POSTFILE writer round-trips AERMOD's output byte for byte. 92 fuzz decks also pass the setup-dump and round-trip checks.
- **DEBUGOPT catalogue.**
  - The 454 names come from DEBUGOPT runs of five cases, and `dbgcatalog.py` reproduces the committed file.
  - The contract's example names are tested to be real.
  - debugdiff matches all 2.59M AERTEST records on replay and pins an injected fault at its first occurrence.
- **Run harness.**
  - The replay stub port passes 11/11.
  - The buggy stub fails every criterion.
  - Stale `.pyc` files can no longer mask edits.
- **Repair loop.** It runs end to end with a scripted fake model: a no-op patch is rejected, a real fix is kept, and provenance verifies.
- **Provenance.** `port/aermod_py` holds only its README. `split.py --verify` accepts only replies backed by a completed, saved interaction.
- **Tests.** `pytest`: 100+ tests pass with the artefacts present. On a fresh clone, `-m "not slow"` passes 40 tests and skips the rest, each with a reason.
- **Live tier A port** (branch `argon/port-tier-a`, run on another machine, published here from its patches).
  - On this machine, `split.py --verify` traces all 12 files.
  - `run_port.py` plus `suite.py` reproduce 7/7: the six tier A cases and `testpm10_stack2`, at slope 1.000000 and p99 relative error 0.
  - The dashboard certifies that port when pointed at that checkout.

## Token counts (tiktoken o200k proxy)

- Tier A: Fortran pack 125,045 tokens code only (the default), or 211,866 with comments. The full port prompt is 165,762, or 252,583 with comments.
- Tier B: Fortran pack 168,261 code only, or 283,216 with comments (162 units). The full port prompt is 208,978, or 323,933 with comments.
- Gemini's `count_tokens` gave 263,773 for the tier A prompt with comments.

## Not verified

- **Argon calls from this machine.** The only live calls ran on another machine (the tier A port and one repair). The Antigravity agent path is untested.
- `--budget-usd`, `--stop-at-passing` and the 30K packet cap are unit-tested only, not exercised in a live repair run. `--budget-usd` has no default prices.
- Tier B (PRIME) has not been ported.
- Apart from that single count_tokens figure, the token counts come from a proxy tokenizer, not Gemini's.
- **EPA rule threshold.** The 1 ± 0.001 slope tolerance is pyaermod's default; EPA's kit states no threshold.
- No R cross-check was run. The slope definitions were read from the R script, not executed.
- HRDOW_STACK1, FLATELEV_FLAT_STK and the holdout have no DEBUGOPT audit.
- Met parsing assumes Python `float()` matches gfortran list-directed reads (true on all cases tested).
- The fixed-scope setup values hold only for the options the glue accepts; other options are rejected, not handled.
- The chunked baseline has only been dry-run tested.
- The CI workflow has not run on GitHub yet.
