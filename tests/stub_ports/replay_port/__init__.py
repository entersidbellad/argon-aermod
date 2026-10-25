"""Test stub: replays our binary's outputs, so run_port and debugdiff must report a perfect match.

Concentrations come from out/ref/<case>/postfile.pst; with debug=True the rows
come from the DEBUGOPT files in out/ref_debug/<case>/.
"""

from pathlib import Path

import numpy as np

import dbgparse
import glue

OUT = Path(__file__).resolve().parents[3] / "out"


def run_case(project: glue.Project, met: glue.Met, setup: dict, *, debug: bool = False) -> glue.Result:
    case = project.inp.parent.name
    rows = [line.split() for line in (OUT / "ref" / case / "postfile.pst").read_text().splitlines()
            if line.strip() and not line.startswith("*")]
    dates = np.array([int(r[8]) for r in rows[::len(project.receptors)]], dtype=np.int64)
    conc = np.array([float(r[2]) for r in rows]).reshape(len(dates), len(project.receptors))
    debug_rows = []
    if debug:
        debug_rows = [(r.date, r.isrc, r.irec, r.comp, r.sub, r.var, r.value)
                      for r in dbgparse.parse_dir(OUT / "ref_debug" / case)]
    return glue.Result(dates=dates, conc=conc, debug=debug_rows)
