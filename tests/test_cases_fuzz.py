"""The case catalogue is in scope, and fuzzed decks pass the binary and glue checks."""

from __future__ import annotations

import random
import warnings

import pytest

import cases as catalog
import fuzz
import glue
from conftest import BINARY, DUMP_BINARY, require


def test_tiers_and_holdout():
    a, b = catalog.tier_cases("A"), catalog.tier_cases("B")
    assert set(a) < set(b)
    assert not any(c.tier == "holdout" for c in b)
    assert [c.name for c in catalog.CASES if c.tier == "holdout"] == ["TESTPM10", "testpm10_stack2"]


@pytest.mark.parametrize("name", [c.name for c in catalog.CASES])
def test_every_deck_is_in_scope(name):
    case = catalog.get(name)
    assert case.inp.exists()
    workdir = require(case.out_dir("ref") / "case.inp", f"run python harness/run_ref.py {name}").parent
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        project = glue.load_project(workdir / "case.inp")
    assert project.FLAT and project.group == case.group and project.group_sources


def test_fuzz_decks_are_deterministic_and_in_scope(tmp_path):
    met = tuple(catalog.get("AERTEST").manifest()["met"])
    one, two = (fuzz.make_deck(random.Random(7), "B", met) for _ in range(2))
    assert one == two
    staged = fuzz.run_ref.case_files(catalog.get("AERTEST"))
    if not all(p.exists() for p in staged):
        pytest.skip("EPA met files missing; run python ref/fetch.py")
    for p in staged:
        (tmp_path / p.name).symlink_to(p.resolve())
    (tmp_path / "case.inp").write_text(one)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        glue.load_project(tmp_path / "case.inp")


def test_fuzzed_decks_match_binary_and_dump(monkeypatch, tmp_path):
    require(BINARY, "run ref/build.sh")
    require(DUMP_BINARY, "run ref/build_dump.sh")
    monkeypatch.setattr(fuzz, "FUZZ_DIR", tmp_path)
    met_case = catalog.get("AERTEST")
    staged = fuzz.run_ref.case_files(met_case)
    rng = random.Random(11)
    for i in range(4):
        text = fuzz.make_deck(rng, "B", tuple(met_case.manifest()["met"]))
        res = fuzz.check_deck(f"t{i}", text, staged, dump=True, port_dir=None)
        assert res.ok, res.problems
