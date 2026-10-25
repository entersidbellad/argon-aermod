"""whatif/: kiln scenario decks, statistics, NAAQS checks, scope guardrails and the API."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

import glue
import run_port
import run_ref
import scenario as sc
import server
from conftest import BINARY, require

CONFIG = sc.load_config()
BASE = sc.baseline(CONFIG, "SO2")


def polar_receptors(config=CONFIG):
    n, dists = config["receptors"]["directions"], config["receptors"]["distances_m"]
    angles = [math.radians(360.0 / n * (j + 1)) for j in range(n)]
    xs = [d * math.sin(a) for a in angles for d in dists]
    ys = [d * math.cos(a) for a in angles for d in dists]
    return SimpleNamespace(AXR=np.array(xs), AYR=np.array(ys))


def fake_record(stack, peak_index=5, port="p" * 64):
    """A ten-day cache record whose unit-rate field peaks at one receptor on five days."""
    rec = polar_receptors()
    hours = 240
    dates = np.array([96010100 + h % 24 + 1 + 100 * (h // 24) for h in range(hours)])
    conc = np.full((hours, len(rec.AXR)), 0.01)
    for hour, value in ((10, 2.0), (30, 1.5), (50, 1.2), (75, 1.0), (100, 0.8)):
        conc[hour, peak_index] = value
    field = sc.Field(stack, rec, dates, conc, np.zeros(hours, dtype=bool), 1.0, port)
    return sc.cache_record(field, CONFIG)


@pytest.fixture
def cache(tmp_path):
    path = tmp_path / "cache"
    path.mkdir()
    for stack in (BASE.stack, sc.Stack(60.0, 3.0, 433.0, 12.0)):
        (path / f"{stack.key}.json").write_text(json.dumps(fake_record(stack)))
    return path


def test_every_fuel_preset_lands_on_the_stack_grid():
    for pollutant in CONFIG["pollutants"]:
        for name, mix in CONFIG["fuel_mix"].items():
            p = sc.preset(CONFIG, pollutant, name)
            assert p["exit_temperature_k"] in CONFIG["grid"]["exit_temperature_k"]
            assert p["emission_rate_gs"] == pytest.approx(
                CONFIG["pollutants"][pollutant]["emission_rate_gs"] * mix["emission_factor"][pollutant])
    assert sc.on_grid(CONFIG, BASE.stack)


def test_a_preset_off_the_grid_is_rejected(tmp_path):
    bad = tmp_path / "kiln.toml"
    bad.write_text(sc.CONFIG_PATH.read_text().replace("exit_temperature_k = 443\n", "exit_temperature_k = 450\n", 1))
    with pytest.raises(ValueError, match="exit_temperature_k"):
        sc.load_config(bad)


def test_deck_is_one_rural_flat_point_source_without_buildings(tmp_path):
    stack = sc.Stack(100.0, 5.0, 443.0, 20.0)
    inp = tmp_path / "case.inp"
    inp.write_text(sc.deck(stack, CONFIG, emission_gs=12.5))
    project = glue.load_project(inp)
    (src,) = project.sources
    assert (src.SRCID, src.building, src.QFLAG) == ("KILN", None, None)
    assert "FLAT" in project.MODELOPT and "URBANOPT" not in inp.read_text()
    rec = project.receptors
    assert len(rec) == CONFIG["receptors"]["directions"] * len(CONFIG["receptors"]["distances_m"])
    assert sorted({round(math.hypot(x, y)) for x, y in zip(rec.AXR, rec.AYR)}) == \
        CONFIG["receptors"]["distances_m"]
    assert re.search(r"SRCPARAM\s+KILN\s+12.5\s+100\s+443\s+20\s+5\b", inp.read_text())


def test_summarize_follows_aermod_period_and_daily_max_rules():
    dates = np.array([96010101, 96010102, 96010124, 96010201, 96010202, 96010301])
    conc = np.array([[1.0], [3.0], [2.0], [5.0], [0.0], [4.0]])
    excluded = np.array([False, False, False, False, True, False])
    s = sc.summarize(dates, conc, excluded)
    assert (s["hours"], s["excluded_hours"], s["days"]) == (6, 1, 3)
    assert s["max_1h"][0] == 5.0
    assert s["period"][0] == pytest.approx(15.0 / 5)
    assert list(s["daily_max_ranks"][0][:4]) == [5.0, 4.0, 3.0, 0.0]


def test_calm_and_missing_hours_are_flagged_like_metext():
    rows = {"IYEAR": [96] * 5, "IMONTH": [1] * 5, "IDAY": [1] * 5, "IHOUR": [1, 2, 3, 4, 5],
            "UREF": [0.0, 3.0, 999.0, 3.0, 3.0], "WDREF": [90.0] * 5, "TA": [290.0, 290.0, 290.0, 0.0, 290.0],
            "OBULEN": [-50.0] * 5, "ZICONV": [500.0] * 5, "ZIMECH": [400.0] * 5,
            "USTAR": [0.3] * 5, "WSTAR": [1.0] * 5}
    met = SimpleNamespace(surface={k: np.array(v) for k, v in rows.items()})
    project = SimpleNamespace(ISDATE=1996010102, IEDATE=1996010105)
    assert list(sc.excluded_hours(project, met)) == [False, True, True, False]


def test_evaluate_scales_the_unit_field_and_checks_the_naaqs(cache):
    inputs = sc.Inputs("SO2", BASE.stack, emission_rate_gs=10.0, background_1h_ugm3=5.0)
    out = sc.evaluate(CONFIG, inputs, cache_dir=cache, current_port="p" * 64)
    assert out["certified"] and out["provenance"]["port_is_current"]
    assert out["max_1h"]["value_ugm3"] == pytest.approx(20.0)
    peak = polar_receptors()
    assert out["max_1h"]["distance_m"] == round(math.hypot(peak.AXR[5], peak.AYR[5]))
    one = out["one_hour"]
    assert one["rank"] == 4 and one["modelled_ugm3"] == pytest.approx(10.0)
    assert one["total_ugm3"] == pytest.approx(15.0) and one["index"] == 5
    assert one["limit_ugm3"] == pytest.approx(75 * 64.066 / 24.45)
    assert one["passes"] and out["annual"]["passes"]

    loud = sc.Inputs("SO2", BASE.stack, emission_rate_gs=300.0, background_annual_ugm3=25.0)
    out = sc.evaluate(CONFIG, loud, cache_dir=cache, current_port="other")
    assert not out["annual"]["passes"] and not out["provenance"]["port_is_current"]
    assert out["annual"]["limit_ugm3"] == pytest.approx(10 * 64.066 / 24.45)


def test_nox_uses_the_no2_standard_and_eighth_highest_day(cache):
    out = sc.evaluate(CONFIG, sc.Inputs("NOX", BASE.stack, emission_rate_gs=1.0), cache_dir=cache)
    assert out["one_hour"]["rank"] == 8 and out["one_hour"]["modelled_ugm3"] == pytest.approx(0.01)
    assert out["one_hour"]["limit_ugm3"] == pytest.approx(100 * 46.0055 / 24.45)
    assert out["annual"]["limit_ppb"] == 53


@pytest.mark.parametrize("change, phrase", [
    ({"building_height_m": 30, "building_width_m": 40, "building_distance_m": 100}, "PRIME"),
    ({"urban": True}, "Urban"),
    ({"complex_terrain": True}, "terrain"),
])
def test_out_of_scope_scenarios_get_a_warning_instead_of_numbers(cache, change, phrase):
    inputs = sc.Inputs("SO2", BASE.stack, emission_rate_gs=10.0, **change)
    out = sc.evaluate(CONFIG, inputs, cache_dir=cache)
    assert (out["certified"], out["status"]) == (False, "out_of_scope")
    assert phrase in " ".join(out["issues"])
    assert "max_1h" not in out and "one_hour" not in out and "field" not in out


def test_a_building_beyond_five_lengths_stays_in_scope(cache):
    inputs = sc.Inputs("SO2", BASE.stack, emission_rate_gs=10.0, building_height_m=30,
                       building_width_m=40, building_distance_m=151)
    assert sc.evaluate(CONFIG, inputs, cache_dir=cache)["certified"]


def test_stacks_that_were_not_precomputed_are_reported(cache):
    for stack in (sc.Stack(61.0, 3.0, 423.0, 12.0), sc.Stack(120.0, 5.0, 443.0, 20.0)):
        out = sc.evaluate(CONFIG, sc.Inputs("SO2", stack, 10.0), cache_dir=cache)
        assert (out["certified"], out["status"]) == (False, "unavailable")
        assert "precomputed" in out["issues"][0]


def test_whatif_api_returns_baseline_and_scenario(cache, monkeypatch):
    monkeypatch.setattr(server, "WHATIF_CACHE", cache)
    client = TestClient(server.app)
    cfg = client.get("/api/whatif/config").json()
    assert cfg["cached"] == 2 and cfg["stacks"] == len(sc.grid(CONFIG))
    assert cfg["naaqs"]["SO2"]["one_hour"]["limit_ugm3"] == pytest.approx(196.5, abs=0.1)
    assert cfg["presets"]["NOX"]["coal_50_alt_50"]["exit_temperature_k"] == 443
    params = {"pollutant": "SO2", "height": 60, "diameter": 3, "temperature": 433, "velocity": 12,
              "emission": 46, "background_1h": 20}
    data = client.get("/api/whatif", params=params).json()
    assert data["baseline"]["certified"] and data["scenario"]["certified"]
    assert data["baseline"]["inputs"]["stack_key"] == BASE.stack.key
    assert data["scenario"]["max_1h"]["value_ugm3"] == pytest.approx(92.0)
    blocked = client.get("/api/whatif", params={**params, "building_height": 30,
                                                "building_width": 40, "building_distance": 50}).json()
    assert not blocked["scenario"]["certified"] and blocked["baseline"]["certified"]
    assert client.get("/api/whatif", params={**params, "pollutant": "CO"}).status_code == 400


def test_committed_cache_covers_the_grid_with_one_port_version():
    records = [sc.load_cached(s) for s in sc.grid(CONFIG)]
    if not any(records):
        pytest.skip("whatif/cache is empty; run python whatif/precompute.py")
    missing = [s.key for s, r in zip(sc.grid(CONFIG), records) if r is None]
    assert not missing, f"not precomputed: {missing}"
    assert len({r["port_sha256"] for r in records}) == 1
    n = CONFIG["receptors"]["directions"] * len(CONFIG["receptors"]["distances_m"])
    assert {len(r["max_1h"]) for r in records} == {n}
    assert {r["hours"] for r in records} == {8784}


def met_or_skip():
    for path in sc.met_files(CONFIG):
        require(path, "run python ref/fetch.py")


SMALL = {"directions": 4, "distances": [400, 1000, 3000]}


@pytest.mark.slow
def test_statistics_match_aermods_own_period_and_daily_max_outputs(tmp_path):
    met_or_skip()
    require(BINARY, "run ref/build.sh")
    stack = sc.Stack(60.0, 3.0, 423.0, 12.0)
    ou = ("   RECTABLE  1  1ST-4TH\n   PLOTFILE  PERIOD  ALL  period.plt\n"
          "   PLOTFILE  1  ALL  1ST  h1.plt\n   PLOTFILE  1  ALL  4TH  h4.plt")
    ref = run_ref.run_deck(sc.deck(stack, CONFIG, pollutid="SO2", extra_ou=ou, **SMALL),
                           sc.met_files(CONFIG), tmp_path / "ref")
    field = sc.run(stack, CONFIG, tmp_path / "port", pollutid="SO2", **SMALL)
    s = sc.summarize(field.dates, field.conc, field.excluded)

    out = (ref.workdir / "case.out").read_text()
    calms = int(re.search(r"A Total of\s+(\d+) Calm Hours", out).group(1))
    missing = int(re.search(r"A Total of\s+(\d+) Missing Hours", out).group(1))
    assert s["excluded_hours"] == calms + missing

    def plotfile(name):
        rows = [l.split() for l in (ref.workdir / name).read_text().splitlines() if not l.startswith("*")]
        return np.array([float(r[2]) for r in rows])

    # The plot files print 5 decimals, so agreement is to half a unit in the last place.
    for name, mine in (("period.plt", s["period"]), ("h1.plt", s["max_1h"]),
                       ("h4.plt", s["daily_max_ranks"][:, 3])):
        np.testing.assert_allclose(mine, plotfile(name), rtol=0, atol=5.01e-6, err_msg=name)


@pytest.mark.slow
def test_port_concentration_is_proportional_to_emission_rate(tmp_path):
    met_or_skip()
    stack = sc.Stack(80.0, 4.0, 433.0, 16.0)
    opts = {**SMALL, "startend": "96 01 01 96 01 31"}
    unit = sc.run(stack, CONFIG, tmp_path / "unit", **opts)
    big = sc.run(stack, CONFIG, tmp_path / "big", emission_gs=37.5, **opts)
    assert unit.port_sha256 == run_port.package_sha256(run_port.PORT_DIR)
    assert unit.conc.max() > 0
    np.testing.assert_allclose(big.conc, 37.5 * unit.conc, rtol=1e-12, atol=1e-15)
