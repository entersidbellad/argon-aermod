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

## Token counts (tiktoken o200k proxy)

- Tier A: Fortran pack 211,866 tokens; full port prompt 252,583.
- Tier B: Fortran pack 283,216 tokens (168,261 code only, 162 units); full port prompt 323,933.

## Not verified

- **Argon has never been called** (no API key here). The Interactions API usage was checked by introspecting google-genai 2.33.0, not by a live call. The Antigravity agent path is untested.
- The token counts use a proxy, not Gemini's tokenizer.
- **EPA rule threshold.** The 1 ± 0.001 slope tolerance is pyaermod's default; EPA's kit states no threshold.
- No R cross-check was run. The slope definitions were read from the R script, not executed.
- HRDOW_STACK1, FLATELEV_FLAT_STK and the holdout have no DEBUGOPT audit.
- Met parsing assumes Python `float()` matches gfortran list-directed reads (true on all cases tested).
- The fixed-scope setup values hold only for the options the glue accepts; other options are rejected, not handled.
- The chunked baseline has only been dry-run tested.
- The CI workflow has not run on GitHub yet.
