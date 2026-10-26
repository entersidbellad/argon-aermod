# Tier A results: gemini-4-argon port of AERMOD 26135

Point sources, flat terrain, rural, 1-hr, no building downwash. Strict comparison
against our gfortran build of EPA AERMOD 26135 (harness/compare.py,
sha256 `f7f31eed0f4718cead4b77384be2eac1779a8fc75c957fefdeaf0eee72461146`). Scored 2026-10-25 14:09 PDT on harness `f53f81f`; re-scored 2026-10-25 16:05 PDT after the import fix (branch `argon/import-fix`, `out/suite_port.json`).

**7 / 7 pass** (6 training cases + tier A holdout). Zero hand edits in `port/aermod_py/`;
`python split.py --verify` traces all 13 files (12 before the import fix added `dateutil.py`) to recorded Argon interactions.

| Case | Role | Result | Slope (best-fit) | Zero/nonzero | P99 rel err | H4H fails | Stable hrs | Convective hrs |
|---|---|---|---|---|---|---|---|---|
| aertest_nobldg | training | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/144 | 100.00%(64h) | 100.00%(32h) |
| CAPPED_STACK2 | training | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/288 | 100.00%(64h) | 100.00%(32h) |
| CAPPED_STACK2C0 | training | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/288 | 100.00%(64h) | 100.00%(32h) |
| CAPPED_STACK2CE | training | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/288 | 100.00%(64h) | 100.00%(32h) |
| HRDOW_STACK1 | training | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/36 | 100.00%(3520h) | 100.00%(5264h) |
| FLATELEV_FLAT_STK | training | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/11 | 100.00%(5144h) | 100.00%(3640h) |
| testpm10_stack2 | holdout | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/36 | 100.00%(20926h) | 100.00%(22898h) |

## Argon calls

| Step | Interaction ID | Packet (count_tokens) | Billed input | Output | Thinking | Cost |
|---|---|---|---|---|---|---|
| One-pass port (thinking high, background) | `v1_ChdkbWZlYXFIRUQ2MmgxTWtQLWFlZDBRYxIXZG1mZWFxSEVENjJoMU1rUC1hZWQwUWM` | 263,773 | 988,112 | 85,741 | 60,591 | $3.44 |
| Repair 1: circular import hrloop <-> metext (`__init__.py`) | `v1_ChdzbXplYXF5RExZN1dqTWNQcF9iQWtBSRIXc216ZWFxeURMWTdXak1jUHBfYkFrQUk` | 1,245 | 1,250 | 1,014 | 11,433 | $0.13 |
| Import fix: `cent_date`/`julian` -> `dateutil.py`, plain `__init__.py` (`agent/edit_step.py`) | `v1_ChdsWDdlYXVUZUNxdU1fUFVQNDQ3ZHdBMBIXbFg3ZWF1VGVDcXVNX1BVUDQ0N2R3QTA` | 21,751 | 21,756 | 20,562 | 1,757 | $0.27 |
| **Total** | | | | | | **$3.84** |

Prices: $2 / 1M input, $10 / 1M output incl. thinking (introductory, through 2026-11-30); no cache hits.
The port call billed ~3.7x its prompt because long decode runs in 64K-token hops and each
hop re-reads the input plus prior output (~264K + 328K + 392K). Port wall time 1,205 s.

## Timeline

1. One-pass port: 12 files, ~240 KB of Python. Compiled, but failed to import (circular import) — 0/6.
2. Repair loop iteration 1: Argon rewrote `__init__.py` to resolve the import cycle; kept (no regressions) — 6/6.
3. Holdout `testpm10_stack2` (never used in repair): pass.
4. Import fix (`agent/runs/import_fix_box_20261025/`): Argon moved CENT_DATE/JULIAN into `dateutil.py`, imported by both `hrloop.py` and `metext.py` (metext: import line only), and replaced the `__init__.py` loader with plain imports. Kept: tier A 6/6 + holdout unchanged, and `import port.aermod_py.metext, port.aermod_py.hrloop` works in either order in a fresh interpreter (with `harness/` on `sys.path` for `glue`).

Provenance: `agent/runs/port_A_box_20261025/`, `agent/runs/repair_A_box/step_001/`, `agent/runs/import_fix_box_20261025/`.
