"""Test stub: all-zero concentrations on the right hours, plus one debug row."""

import numpy as np

import glue


def run_case(project: glue.Project, met: glue.Met, setup: dict, *, debug: bool = False) -> glue.Result:
    dates = glue.expected_dates(project, met)
    debug_rows = [(int(dates[0]), 1, 1, "PLUME", "", "UEFF", 0.0)] if debug else []
    return glue.Result(dates=dates, conc=np.zeros((len(dates), len(project.receptors))), debug=debug_rows)
