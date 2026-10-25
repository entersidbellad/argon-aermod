"""Test stub: replays out/ref/<case>/postfile.pst so run_port must reproduce it byte for byte."""

from pathlib import Path

import numpy as np

import glue

REF = Path(__file__).resolve().parents[3] / "out" / "ref"


def run_case(project: glue.Project, met: glue.Met, setup: dict, *, debug: bool = False) -> glue.Result:
    rows = [line.split() for line in (REF / project.inp.parent.name / "postfile.pst").read_text().splitlines()
            if line.strip() and not line.startswith("*")]
    dates = np.array([int(r[8]) for r in rows[::len(project.receptors)]], dtype=np.int64)
    conc = np.array([float(r[2]) for r in rows]).reshape(len(dates), len(project.receptors))
    return glue.Result(dates=dates, conc=conc)
