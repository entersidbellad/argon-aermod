"""Test stub for the repair loop: a replay of our binary with a planted bug.

With BUG = 1.0 every concentration is 0.1% high and every XFINAL debug value is
off by 1 m; the repair test's scripted "model" replies with BUG = 0.0.
"""

from pathlib import Path

import numpy as np

import dbgparse
import glue

OUT = Path(glue.__file__).resolve().parents[1] / "out"
BUG = 1.0


def pcalc_rows(rows: list[tuple]) -> list[tuple]:
    """SUBROUTINE PCALC (calc1.f)."""
    return [r[:6] + (r[6] + BUG,) if r[5] == "XFINAL" else r for r in rows]


def run_case(project: glue.Project, met: glue.Met, setup: dict, *, debug: bool = False) -> glue.Result:
    case = project.inp.parent.name
    rows = [line.split() for line in (OUT / "ref" / case / "postfile.pst").read_text().splitlines()
            if line.strip() and not line.startswith("*")]
    dates = np.array([int(r[8]) for r in rows[::len(project.receptors)]], dtype=np.int64)
    conc = np.array([float(r[2]) for r in rows]).reshape(len(dates), len(project.receptors))
    debug_rows = []
    if debug:
        debug_rows = pcalc_rows([(r.date, r.isrc, r.irec, r.comp, r.sub, r.var, r.value)
                                 for r in dbgparse.parse_dir(OUT / "ref_debug" / case)])
    return glue.Result(dates=dates, conc=conc * (1.0 + 1e-3 * BUG), debug=debug_rows)
