# AERMOD Python Port

Gemini 4 Argon (`gemini-4-argon`, 1M-token context) ports a scoped slice of EPA AERMOD 26135 from Fortran to Python in one full-context pass. An automated repair loop then fixes divergences against our compiled reference binary. Every Python file under `port/aermod_py/` must come from a recorded Argon interaction; `split.py --verify` checks this.

## Scope

- POINT sources, FLAT terrain, rural, concentration, 1-hr averages.
- **Tier A**: no building downwash. **Tier B**: adds PRIME.
- Not ported: SETUP (input parsing) and output. The human-written `harness/glue.py` parses the deck with pyaermod, builds every SETUP-assigned value the physics reads (checked bit for bit against `SETUP.DMP` from an instrumented AERMOD build), and writes the POSTFILE.

## Quickstart

```bash
pip install -r requirements.txt
make ref          # fetch EPA source + test cases (checksummed), build ref/aermod and ref/aermod_dump
make refs dumps debug-refs   # oracles, SETUP.DMP ground truth, DEBUGOPT runs
python pack.py    # context/tier_{A,B}.txt and context/tokens.json
make test         # full pytest suite (make test-fast skips the slow DEBUGOPT/e2e tests)

export GEMINI_API_KEY=...
python agent/port.py --tier B                # one pass; replies saved under agent/runs/
python agent/repair_loop.py --tier B         # repair against the tier's training cases
make suite-port                              # run the port on every case -> out/suite_port.json
make verify                                  # provenance of port/aermod_py
make serve                                   # read-only dashboard on 127.0.0.1:8000
```

`python agent/port.py --tier B --dry-run` writes the prompt and counts tokens without calling the API.

## Results

The first live run is on branch [`argon/port-tier-a`](https://github.com/entersidbellad/argon-aermod/tree/argon/port-tier-a), with its run folders under `agent/runs/` and `results/tier_A.md`.
- The one-pass tier A port did not import at first because of a circular import.
- One repair iteration fixed it. After that, all 6 tier A cases and the `testpm10_stack2` holdout pass the strict compare (slope 1.000000, p99 relative error 0).
- `split.py --verify` traces all 12 files to recorded Argon interactions.
- The total Gemini spend was $3.57.

To browse that run: `git worktree add ../argon argon/port-tier-a && python server.py --root ../argon`.

## Cost controls

- **Comment-stripped Fortran by default.** `agent/port.py` sends `context/tier_<T>_code.txt` unless you pass `--with-comments`.
- **Continuation billing.** In background mode, Argon decodes in 64K-token hops, and every hop bills the full input again.
  - The box run requested more than 64K output tokens, so its 264K-token prompt billed 988K input tokens.
  - `port.py` therefore warns on stderr whenever `--max-output-tokens` is above 65,536.
  - It also records `expected_input_multiplier` in `run.json`.
- **Repair loop limits** (`agent/repair_loop.py`):
  - `--budget-usd` stops before a request would pass the cap. The spend is computed from each reply's usage, so it needs `--usd-per-mtok-input`/`--usd-per-mtok-output` or `ARGON_USD_PER_MTOK_INPUT`/`_OUTPUT`.
  - `--stop-at-passing N` stops once N training cases pass.
  - Every repair packet must fit within 30K tokens. Optional files that don't fit are dropped with a note; a packet whose target file alone is too large is not sent.

## Verification rules (`harness/compare.py`, frozen; `make freeze` prints its sha256)

Both rules must pass.

**EPA rule.** Best-fit slope within 1 ± 0.001, against EPA's shipped POSTFILE, or our binary's for the two cases with no EPA file (`aertest_nobldg`, `testpm10_stack2`). EPA's 26135 kit gives no numeric threshold and uses "best-fit slope" for three different quantities, so all three must be in tolerance:
- the through-origin slope (`pyaermod.regulatory_parity.score_postfile_pair`);
- the OLS line `Compare_AERMOD_test_cases.R` draws;
- the mean ratio the kit's instructions call the BestFitSlope value.

**Strict rule**, always against our compiled binary:
- every row present in both files;
- zero/nonzero agreement ≥ 99.9%;
- p99 relative error ≤ 1e-4 over values ≥ 1% of the case max;
- per-receptor H4H design value within 1e-4 relative.

Our gfortran build against EPA's shipped files (`harness/suite.py --vs-epa`): identical on every case except CAPPED_STACK1C0 (362 of 27,648 values differ, max 6.67 µg/m³, slopes 0.99999) and TESTPM10 (1,243 of 1,577,664, max 0.026). Ref-vs-ref through `compare.py` passes 11/11.

## Cases (`harness/cases.py`)

| Tier | Cases |
|---|---|
| A | aertest_nobldg, CAPPED_STACK2, CAPPED_STACK2C0, CAPPED_STACK2CE, HRDOW_STACK1, FLATELEV_FLAT_STK |
| B (adds) | AERTEST, CAPPED_STACK1C0, ALLSRCS_STACKDW |
| Holdout | TESTPM10, testpm10_stack2 (never shown to the repair loop) |

`harness/fuzz.py` generates random in-scope decks on real met and checks each against the binary, the SETUP dump and the POSTFILE round trip (and the port, with `--port`).

## Token counts (tiktoken o200k proxy, not Gemini's tokenizer)

| | Fortran pack, code only (default) | with comments | Full port prompt, code only (default) | with comments |
|---|---|---|---|---|
| Tier A (120 units) | 125,045 | 211,866 | 165,762 | 252,583 |
| Tier B (162 units) | 168,261 | 283,216 | 208,978 | 323,933 |

Gemini's own `count_tokens` gave 263,773 tokens for the tier A prompt with comments on the box run.

The chunked baseline (`agent/baselines/chunked.py`, 128K cap) needs 12 requests for tier B.

## Port contract (`prompts/contract.md`)

```python
run_case(project: glue.Project, met: glue.Met, setup: dict, *, debug=False) -> glue.Result
```

`Result(dates, conc[hour, receptor], debug)`. With `debug=True`, `debug` is a list of `(KURDAT, ISRC, IREC, COMP, SUB, VAR, value)` rows named after AERMOD's DEBUGOPT output. The 454 valid names in `prompts/debug_vars.md` are generated by `harness/dbgcatalog.py` from real DEBUGOPT runs; `harness/debugdiff.py` reports the first divergent record against the reference.

## Repair loop (`agent/repair_loop.py`)

1. Score the training cases and find the first problem: a crash, or the first divergent DEBUGOPT record.
2. Send Argon the record, the met for that hour, the Fortran unit and the Python files translating it.
3. Patches may touch at most 2 files.
4. A patch is kept only if nothing regresses and the target passes or its first problem moves later. Otherwise it is reverted.
5. After 3 rejections on the same target, escalate to a full-context consult.

Kept patches are recorded in `files.json` next to the reply. Each iteration is logged under `agent/runs/<run>/iter_NNN/`.

- A crash packet includes the port modules named in the traceback, innermost first.
- A patch that crashes during evaluation is rolled back.

## Dashboard (`make serve`, or `python server.py --root CHECKOUT`)

The dashboard is read-only and computes everything from files on disk at each page load. It has three screens:
- **Port** lists every run under `agent/runs/`, meaning any folder with `run.json` or `result.json`.
  - For each run it shows the Argon interactions with token usage, the files each one wrote, and the repair decisions.
  - Costs come from the "Argon calls" table in `results/tier_*.md`.
- **Proof** shows:
  - `compare.py`'s sha256 against `harness/compare.sha256`;
  - the per-case grid, from `out/suite_port.json` if present, otherwise from the committed `results/tier_*.md`, otherwise from the latest repair `result.json`;
  - every port file traced to the reply and interaction ID that produced it (`split.trace`).
- **Decision** certifies only if every criterion holds:
  - the suite was scored with the approved `compare.py`;
  - it was scored against the current port version;
  - every tier A case passes both rules;
  - the provenance is clean.

## Layout

```
ref/        fetch.py, build.sh, build_dump.sh (EPA download + gfortran builds)
cases/      reduced decks per case (committed)
harness/    glue, run_ref, run_port, compare (frozen), suite, debugdiff, dbgparse, dbgcatalog, fuzz, setup_inputs
prompts/    contract, port, repair, consult, chunked_port, debug_vars (generated)
agent/      argon (Interactions API client), port, repair_loop, baselines/chunked
port/aermod_py/   Argon output only (plus a human README)
tests/      pytest; stub_ports/ hold replay, zero and buggy fake ports
server.py, ui/    read-only dashboard
```
