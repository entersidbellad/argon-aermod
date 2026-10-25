"""harness/glue.py against our binary: receptors, POSTFILE format, SETUP values, dates."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

import cases as catalog
import glue
import setup_inputs
from conftest import oracle, require

CASE_NAMES = [c.name for c in catalog.CASES]


def load(name: str, who: str = "ref") -> tuple[glue.Project, glue.Met]:
    workdir = catalog.get(name).out_dir(who)
    require(workdir / "case.inp", f"run python harness/run_ref.py {name}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        project = glue.load_project(workdir / "case.inp")
    return project, glue.load_met(project, workdir)


def data_rows(path) -> list[str]:
    return [l for l in path.read_text().splitlines() if l.strip() and not l.startswith("*")]


def test_stodbl_reproduces_aermods_digit_by_digit_rounding():
    assert glue.stodbl("62.26") == (62.260000000000005, 1)    # float("62.26") is 62.26
    assert glue.stodbl("500.") == (500.0, 1)
    assert glue.stodbl("1.5E2") == (150.0, 1)
    with pytest.raises(ValueError):
        glue.stodbl("1,000")


def test_nint_rounds_half_away_from_zero():
    assert [glue._nint(x) for x in (2.5, -2.5, 0.49999, 1.5)] == [3, -3, 0, 2]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_postfile_round_trip_matches_binary(name, tmp_path):
    """Receptor expansion (order, coordinates, elevations) and the POSTFILE FORMAT."""
    project, met = load(name)
    ref = require(oracle(name), f"run python harness/run_ref.py {name}")
    rows = data_rows(ref)
    nrec = len(project.receptors)
    assert len(rows) % nrec == 0
    conc = np.array([float(r.split()[2]) for r in rows]).reshape(-1, nrec)
    dates = glue.expected_dates(project, met)
    assert [int(r.split()[8]) for r in rows[::nrec]] == dates.tolist()
    out = tmp_path / "postfile.pst"
    glue.write_postfile(out, project, dates, conc)
    assert data_rows(out) == rows


@pytest.mark.parametrize("name", CASE_NAMES)
def test_setup_values_match_aermods_dump(name):
    """Every SETUP input bit for bit against SETUP.DMP from ref/aermod_dump."""
    workdir = catalog.get(name).out_dir("setup_dump")
    dump = require(workdir / "SETUP.DMP", "run ref/aermod_dump on the case (ref/build_dump.sh)")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        project = glue.load_project(workdir / "case.inp")
    values = glue.setup_values(project, glue.load_met(project, workdir))
    reference = setup_inputs.read_dump(dump)
    assert set(reference) == set(glue.SETUP_INPUT_NAMES)
    assert setup_inputs.compare_dump(values, reference, glue.SETUP_SCRATCH) == []


def _variant(tmp_path, name: str, old: str, new: str):
    workdir = catalog.get(name).out_dir("ref")
    require(workdir / "case.inp", f"run python harness/run_ref.py {name}")
    text = (workdir / "case.inp").read_text()
    assert old in text
    for f in workdir.iterdir():
        if f.name != "case.inp":
            (tmp_path / f.name).symlink_to(f.resolve())
    (tmp_path / "case.inp").write_text(text.replace(old, new, 1))
    return tmp_path / "case.inp"


@pytest.mark.parametrize("old,new,match", [
    ("MODELOPT  CONC   FLAT", "MODELOPT  CONC", "FLAT"),
    ("MODELOPT  CONC   FLAT", "MODELOPT  CONC   FLAT  NOSTD", "MODELOPT"),
    ("RUNORNOT RUN", "RUNORNOT RUN\n   URBANOPT  100000", "keywords"),
])
def test_out_of_scope_decks_are_rejected(tmp_path, old, new, match):
    inp = _variant(tmp_path, "AERTEST", old, new)
    with warnings.catch_warnings(), pytest.raises(ValueError, match=match):
        warnings.simplefilter("ignore")
        glue.load_project(inp)


def test_missing_setup_input_is_an_error(monkeypatch):
    project, met = load("AERTEST")
    monkeypatch.setattr(glue, "SETUP_INPUT_NAMES", glue.SETUP_INPUT_NAMES + ("NOT_A_VARIABLE",))
    with pytest.raises(Exception, match="NOT_A_VARIABLE"):
        glue.setup_values(project, met)
