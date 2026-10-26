"""pack.py scope and setup_inputs.py consistency against the EPA source."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

import pack
import setup_inputs
from conftest import SOURCE, require


@pytest.fixture(scope="module", autouse=True)
def source():
    require(SOURCE, "run python ref/fetch.py")


def names(tier: str) -> set[str]:
    return {u.name for u in pack.select_units(tier)[0]}


def test_tier_b_reaches_hrloop_physics_and_prime_initialisers():
    b = names("B")
    assert {"HRLOOP", "METEXT", "PCALC", "IBLVAL", "DELTAH", "PRMCALC", "NUMPR1", "PRIME1",
            "MAIN1"} <= b
    assert not (b & pack.EXCLUDE_COMMON)


def test_tier_a_drops_prime():
    a = names("A")
    assert "PCALC" in a and not (a & pack.EXCLUDE_TIER_A)
    assert a < names("B")


def test_committed_index_matches_the_source():
    for tier in ("A", "B"):
        committed = {u["name"]: (u["file"], u["start"], u["end"]) for u in pack.load_index(tier).values()}
        current = {u.name: (u.file, u.start, u.end) for u in pack.select_units(tier)[0]}
        assert committed == current, f"context/index_tier_{tier}.json is stale; run python pack.py"


def test_fortran_unit_returns_the_whole_unit():
    text = pack.fortran_unit("PCALC")
    assert text.lstrip().startswith("SUBROUTINE PCALC")
    assert text.rstrip().upper().endswith("END")


def test_committed_setup_inputs_match_the_source():
    committed = json.loads(setup_inputs.OUT_JSON.read_text())
    current = [asdict(v) for v in setup_inputs.find_inputs()]
    assert committed == current, "harness/setup_inputs.json is stale; run python harness/setup_inputs.py"
