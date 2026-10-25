"""harness/compare.py: each EPA and strict criterion, on perturbed copies of the AERTEST oracle."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

import cases as catalog
import compare
import glue
from conftest import oracle, require


@pytest.fixture(scope="module")
def aertest():
    workdir = catalog.get("AERTEST").out_dir("ref")
    ref = require(oracle("AERTEST"), "run python harness/run_ref.py AERTEST")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        project = glue.load_project(workdir / "case.inp")
    met = glue.load_met(project, workdir)
    rows = [l for l in ref.read_text().splitlines() if l.strip() and not l.startswith("*")]
    conc = np.array([float(r.split()[2]) for r in rows]).reshape(-1, len(project.receptors))
    return project, glue.expected_dates(project, met), conc, ref


def write(tmp_path, aertest, conc, dates=None, name="cand.pst"):
    project, all_dates, _, _ = aertest
    path = tmp_path / name
    glue.write_postfile(path, project, all_dates if dates is None else dates, conc)
    return path


def judge(cand, ref, epa=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compare.compare_case(cand, ref, epa=epa)


def test_identical_passes_everything(tmp_path, aertest):
    _, _, conc, ref = aertest
    res = judge(write(tmp_path, aertest, conc), ref)
    assert res.passes
    assert (res.epa.slope, res.epa.slope_ols, res.epa.mean_ratio) == pytest.approx((1, 1, 1), abs=1e-12)
    assert res.strict.p99_rel_err == 0 and res.strict.h4h_n_fail == 0


def test_within_strict_tolerance_passes(tmp_path, aertest):
    _, _, conc, ref = aertest
    res = judge(write(tmp_path, aertest, conc * (1 + 5e-5)), ref)
    assert res.epa.passes and res.strict.passes


def test_slope_outside_tolerance_fails_epa_rule(tmp_path, aertest):
    _, _, conc, ref = aertest
    res = judge(write(tmp_path, aertest, conc * 1.002), ref)
    assert res.epa.slope == pytest.approx(1.002, rel=1e-4)
    assert not res.epa.passes and not res.passes


def test_ols_and_mean_ratio_follow_epas_orientation(tmp_path, aertest):
    """lm(candidate ~ reference) as the R script plots; conc1mean/conc2mean with conc1 = reference."""
    _, _, conc, ref = aertest
    res = judge(write(tmp_path, aertest, conc * 2.0), ref)
    assert res.epa.slope_ols == pytest.approx(2.0, rel=1e-4)
    assert res.epa.mean_ratio == pytest.approx(0.5, rel=1e-4)


def test_epa_rule_uses_epas_file_and_strict_rule_uses_our_binary(tmp_path, aertest):
    _, _, conc, ref = aertest
    epa = write(tmp_path, aertest, conc * 1.002, name="epa.pst")
    res = judge(write(tmp_path, aertest, conc), ref, epa=epa)
    assert res.epa.against == "EPA reference POSTFILE" and not res.epa.passes
    assert res.strict.passes


def test_missing_hour_fails_coverage(tmp_path, aertest):
    _, dates, conc, ref = aertest
    res = judge(write(tmp_path, aertest, conc[1:], dates=dates[1:]), ref)
    assert res.strict.n_ref_only == conc.shape[1] and not res.strict.coverage_ok
    assert not res.passes


def test_zero_nonzero_disagreement_fails(tmp_path, aertest):
    _, _, conc, ref = aertest
    cand = conc.copy()
    nz = np.flatnonzero(cand > 0)
    cand.flat[nz[:int(0.002 * cand.size) + 1]] = 0.0
    res = judge(write(tmp_path, aertest, cand), ref)
    assert res.strict.zero_agreement < compare.ZERO_AGREEMENT_MIN and not res.strict.zero_ok


def test_p99_counts_only_values_above_one_percent_of_max(tmp_path, aertest):
    _, _, conc, ref = aertest
    cand = conc.copy()
    small = (cand > 0) & (cand < 0.005 * cand.max())
    assert small.any()
    cand[small] *= 1.5
    res = judge(write(tmp_path, aertest, cand), ref)
    assert res.strict.p99_ok


def test_one_receptors_design_value_off_fails_h4h_only(tmp_path, aertest):
    _, _, conc, ref = aertest
    cand = conc.copy()
    h, r = np.unravel_index(np.argmax(cand), cand.shape)
    cand[h, r] *= 1 + 1e-3
    res = judge(write(tmp_path, aertest, cand), ref)
    assert res.strict.p99_ok and res.strict.zero_ok and res.strict.coverage_ok
    assert res.strict.h4h_n_fail == 1 and not res.strict.passes
