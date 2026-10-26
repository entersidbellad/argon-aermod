# Tier B results: gemini-4-argon port of AERMOD 26135 with PRIME

Point sources, flat terrain, rural, 1-hr, with PRIME building downwash. Strict comparison
against our gfortran build of EPA AERMOD 26135 (harness/compare.py,
sha256 `f7f31eed0f4718cead4b77384be2eac1779a8fc75c957fefdeaf0eee72461146`). Scored 2026-10-25 17:17:00 PDT on harness `ba57d20` (branch `argon/port-tier-b`)
(`out/suite_port.json`, port sha256 `e7210c69e6c09e8a`).

**11 / 11 pass** (9 tier B training cases including tier A, plus both holdouts). Zero hand edits in
`port/aermod_py/`; `python split.py --verify` traces all 18 files to recorded Argon interactions.
The repair loop was not needed: its first scoring (`agent/runs/repair_B_box_20261025/scoreboard.jsonl`)
found all 9 training cases passing, so it made no Argon calls and was stopped.

| Case | Role | Result | Slope (best-fit) | Zero/nonzero | P99 rel err | H4H fails | Stable hrs | Convective hrs |
|---|---|---|---|---|---|---|---|---|
| aertest_nobldg | training (A) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/144 | 100.00%(64h) | 100.00%(32h) |
| CAPPED_STACK2 | training (A) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/288 | 100.00%(64h) | 100.00%(32h) |
| CAPPED_STACK2C0 | training (A) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/288 | 100.00%(64h) | 100.00%(32h) |
| CAPPED_STACK2CE | training (A) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/288 | 100.00%(64h) | 100.00%(32h) |
| HRDOW_STACK1 | training (A) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/36 | 100.00%(3520h) | 100.00%(5264h) |
| FLATELEV_FLAT_STK | training (A) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/11 | 100.00%(5144h) | 100.00%(3640h) |
| AERTEST | training (B) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/144 | 100.00%(64h) | 100.00%(32h) |
| CAPPED_STACK1C0 | training (B) | PASS | 0.999991/0.999992/1.000010 | 100.000% | 0.00e+00 | 0/288 | 100.00%(64h) | 100.00%(32h) |
| ALLSRCS_STACKDW | training (B) | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/331 | 100.00%(64h) | 100.00%(32h) |
| TESTPM10 | holdout (B) | PASS | 1.000000/1.000000/1.000001 | 100.000% | 0.00e+00 | 0/36 | 100.00%(20926h) | 100.00%(22898h) |
| testpm10_stack2 | holdout | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/36 | 100.00%(20926h) | 100.00%(22898h) |

CAPPED_STACK1C0's EPA slopes (0.99999) reflect our binary vs EPA's shipped POSTFILE (362 values differ,
see README); against our binary the strict rule is exact (p99 0).

## Argon calls

| Step | Interaction ID | Packet (count_tokens) | Billed input | Output | Thinking | Cost |
|---|---|---|---|---|---|---|
| Chunk 1/5: prime_state.py + prime_base.py | `v1_ChczWVhlYXEtdkNvYXoxTWtQd3JfSzBRdxIXM1lYZWFxLXZDb2F6MU1rUHdyX0swUXc` | 60,782 | 60,787 | 14,386 | 37,506 | $0.64 |
| Chunk 2/5: prime_wake.py | `v1_ChdJWXJlYXZHSERiblgtc0FQaXVEQmtRRRIXSVlyZWF2R0hEYm5YLXNBUGl1REJrUUU` | 84,830 | 84,835 | 24,553 | 19,440 | $0.61 |
| Chunk 3/5: prime_rise.py | `v1_Chc4STNlYXZUWE9MZXE5TW9QNTlEMW1RNBIXOEkzZWF2VFhPTGVxOU1vUDU5RDFtUTQ` | 60,519 | 60,524 | 11,821 | 25,816 | $0.50 |
| Chunk 4/5: prmcalc.py | `v1_ChdZcERlYXRHY09QQ3Y5TW9QcnNxU3FBYxIXWXBEZWF0R2NPUEN2OU1vUHJzcVNxQWM` | 58,702 | 58,707 | 6,034 | 16,927 | $0.35 |
| Chunk 5/5: wire PCALC + run_case (first eval reverted; same reply re-applied after the name fix) | `v1_ChdYNUxlYXFxREpOSFBfdU1QZzVYQjJBRRIXWDVMZWFxcURKTkhQX3VNUGc1WEIyQUU` | 77,845 | 77,850 | 19,595 | 10,054 | $0.45 |
| Name fix: prime_base.py | `v1_ChdscFBlYXRxZEJ1ckktc0FQeTdmbi1BSRIXbHBQZWF0cWRCdXJJLXNBUHk3Zm4tQUk` | 12,424 | 12,429 | 12,027 | 0 | $0.15 |
| Name fix: prime_wake.py | `v1_ChZsWlBlYW82a09zN2Utc0FQNFp1UVNREhZsWlBlYW82a09zN2Utc0FQNFp1UVNR` | 22,564 | 22,569 | 22,116 | 0 | $0.27 |
| Name fix: prime_rise.py | `v1_ChdscFBlYXAtbUFjRy14ZElQcTYyTjZBcxIXbHBQZWFwLW1BY0cteGRJUHE2Mk42QXM` | 9,600 | 9,605 | 9,187 | 0 | $0.11 |
| Name fix: prmcalc.py | `v1_ChdsWlBlYXR1ME5QYjctc0FQNTh6TDJBWRIXbFpQZWF0dTBOUGI3LXNBUDU4ekwyQVk` | 6,605 | 6,610 | 6,052 | 0 | $0.07 |
| **Total** | | 393,871 | 393,916 | 125,771 | 109,743 | **$3.14** |

Prices: $2 / 1M input, $10 / 1M output incl. thinking (introductory, through 2026-11-30); no cache hits.
Every request stayed under 64K output tokens, so no continuation re-billing (billed input = prompt + 5).
Project total so far: $3.57 (tier A) + $0.27 (import fix) + $3.14 (tier B) = $6.98.

## How it was ported

The tier B pack (~209K tokens) was split along the PRIME call graph, leaves first, so each request
saw the exact signatures of what it calls (`agent/edit_step.py`, plan in `prompts/tasks/tier_b/plan.md`):
shared contract/glue/SETUP/debug context (42K) + the port's API index + comment-stripped Fortran for the chunk.

1. `prime_state.py` (PRIME_* modules as `PrimeState`, carried as `state.prime`) and `prime_base.py` (26 leaf units).
2. `prime_wake.py`: WAKE_U_TURB, WAKE_TURB, WAKE_U, WAKE_SIG, WAKE_DFSN, WAKE_DFSN2, WAKE_FQC, CAV_SRC.
3. `prime_rise.py`: NUMRISE, WAKE_DBG, PRMDELH.
4. `prmcalc.py`: PRMCALC, GAMCALC, PRMHEFF, PRM_PCHI, PRM_PLUME.
5. PCALC in `calc1.py` and `run_case` wired to PRIME. Its first evaluation crashed every case: the plan
   told chunks 1-4 that MAIN1 names are upper case, but `AermodState` spells some options in mixed case
   (`L_ORD_Turb`, `L_AWMA_UTurbHX`, `PRMVAL_Src1`, ...). `agent/attr_check.py` listed the 11 names,
   one small recorded Argon edit per file renamed them, and the saved chunk 5 reply was re-applied
   unchanged (`edit_step.py --apply-reply`, no new call). Result: 11/11.

Each kept step ran the tier A cases + `testpm10_stack2` (no regressions) and import checks in a fresh
interpreter. TESTPM10 (5 years, PRIME) takes ~21 min in the port vs ~5.5 min without PRIME.

Provenance: `agent/runs/tierB_c1_base/`, `tierB_c2_wake/`, `tierB_c3_rise/`, `tierB_c4_prmcalc/`,
`tierB_c5_wire/` (files.json entry from the re-apply), `tierB_fix_names_*/`, `repair_B_box_20261025/`.
Prompts (`prompt.txt`) embed EPA source and are not committed.
