"""AERMOD 26135 Python port: package entry point."""

from __future__ import annotations

import numpy as xp
import glue

from .state import AermodState
from .prime_state import PrimeState
from .prime_base import numpr1, prime1
from .hrloop import hrloop


def run_case(
    project: glue.Project,
    met: glue.Met,
    setup: dict,
    *,
    debug: bool = False,
) -> glue.Result:
    """Run HRLOOP and all in-scope AERMOD physics for a prepared case."""
    state = AermodState.from_setup(project, met, setup, debug=debug)
    state.prime = PrimeState()
    numpr1(state)
    prime1(state)
    hrloop(state)
    dates = xp.asarray(state.dates_out, dtype=xp.int64)
    if len(state.conc_out) > 0:
        conc = xp.stack(state.conc_out, axis=0).astype(xp.float64)
    else:
        conc = xp.zeros((0, state.NUMREC), dtype=xp.float64)
    return glue.Result(dates=dates, conc=conc, debug=state.debug_rows)
