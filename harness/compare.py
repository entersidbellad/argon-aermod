#!/usr/bin/env python3
"""Judge a candidate POSTFILE. This file is frozen: ``make freeze`` prints its sha256.

Two rules, both must pass:

EPA rule
    Best-fit slope through the origin of (reference, candidate) paired on
    (x, y, date, ave, grp), computed by ``pyaermod.regulatory_parity.
    score_postfile_pair`` (EPA's Compare_AERMOD_test_cases.R metric), must be
    within 1 +/- 0.001. Reference = EPA's shipped POSTFILE when the case has
    one, otherwise our compiled binary's POSTFILE.

Strict rule (always against OUR compiled binary's POSTFILE, never EPA's file,
because our gfortran build already differs from EPA's shipped files by more
than 1e-4 on some cases)
    * every (x, y, date, ave, grp) row appears in both files;
    * zero/nonzero agreement >= 99.9% of paired values;
    * p99 of |cand - ref| / ref <= 1e-4 over values with ref >= 1% of case max;
    * per-receptor H4H design value within 1e-4 relative, for every receptor.
      The design value is ``pyaermod.design_values.so2_1hr_design_value``: the
      99th-percentile daily-max 1-hr value (4th-highest daily max in a full
      year; the highest daily max for records shorter than ~100 days).

Pass rates are also reported split by stable (L > 0) and convective (L < 0)
hours, using the Monin-Obukhov length from the case's AERMET .sfc file.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from pyaermod.design_values import so2_1hr_design_value
from pyaermod.postfile import read_postfile
from pyaermod.regulatory_parity import DEFAULT_SLOPE_TOLERANCE, score_postfile_pair

KEYS = ["x", "y", "date", "ave", "grp"]
SLOPE_TOL = DEFAULT_SLOPE_TOLERANCE      # 0.001
ZERO_AGREEMENT_MIN = 0.999
REL_TOL = 1e-4
SIGNIFICANT_FRACTION = 0.01
PERCENTILE = 99.0


@dataclass
class EpaResult:
    against: str
    n_paired: int
    slope: float
    max_abs_error: float
    passes: bool


@dataclass
class StrictResult:
    n_paired: int
    n_ref_only: int
    n_cand_only: int
    zero_agreement: float
    n_significant: int
    p99_rel_err: float
    frac_within_tol: float          # share of significant values within REL_TOL
    max_abs_diff: float
    zero_ok: bool
    p99_ok: bool
    coverage_ok: bool
    h4h_n_receptors: Optional[int] = None
    h4h_max_rel_diff: Optional[float] = None
    h4h_n_fail: Optional[int] = None
    h4h_ok: Optional[bool] = None

    @property
    def passes(self) -> bool:
        return self.coverage_ok and self.zero_ok and self.p99_ok and self.h4h_ok is not False


@dataclass
class CaseComparison:
    case: str
    epa: EpaResult
    strict: StrictResult
    by_stability: dict = field(default_factory=dict)

    @property
    def passes(self) -> bool:
        return self.epa.passes and self.strict.passes

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strict"]["passes"] = self.strict.passes
        d["passes"] = self.passes
        return d


def load(path: Path | str) -> pd.DataFrame:
    df = read_postfile(path).data
    return df[KEYS + ["concentration"]]


def pair(ref: pd.DataFrame, cand: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    merged = ref.merge(cand, on=KEYS, how="outer", suffixes=("_ref", "_cand"), indicator=True)
    ref_only = int((merged["_merge"] == "left_only").sum())
    cand_only = int((merged["_merge"] == "right_only").sum())
    both = merged[merged["_merge"] == "both"].drop(columns="_merge")
    return both, ref_only, cand_only


def design_values(df: pd.DataFrame) -> pd.DataFrame:
    years = df["date"].astype(str).str[:2].nunique()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return so2_1hr_design_value(df, n_years=years)[["x", "y", "concentration"]]


def strict_metrics(paired: pd.DataFrame, ref_only: int, cand_only: int,
                   case_max: float) -> StrictResult:
    r = paired["concentration_ref"].to_numpy(dtype=np.float64)
    c = paired["concentration_cand"].to_numpy(dtype=np.float64)
    n = len(r)
    zero_agreement = float(np.mean((r > 0) == (c > 0))) if n else 1.0
    sig = r >= SIGNIFICANT_FRACTION * case_max if case_max > 0 else np.zeros(n, bool)
    rel = np.abs(c[sig] - r[sig]) / r[sig]
    p99 = float(np.percentile(rel, PERCENTILE)) if rel.size else 0.0
    return StrictResult(
        n_paired=n,
        n_ref_only=ref_only,
        n_cand_only=cand_only,
        zero_agreement=zero_agreement,
        n_significant=int(sig.sum()),
        p99_rel_err=p99,
        frac_within_tol=float(np.mean(rel <= REL_TOL)) if rel.size else 1.0,
        max_abs_diff=float(np.max(np.abs(c - r))) if n else 0.0,
        zero_ok=zero_agreement >= ZERO_AGREEMENT_MIN,
        p99_ok=p99 <= REL_TOL,
        coverage_ok=ref_only == 0 and cand_only == 0,
    )


def strict_compare(ref: pd.DataFrame, cand: pd.DataFrame) -> StrictResult:
    paired, ref_only, cand_only = pair(ref, cand)
    case_max = float(ref["concentration"].max()) if len(ref) else 0.0
    result = strict_metrics(paired, ref_only, cand_only, case_max)
    dv = design_values(ref).merge(design_values(cand), on=["x", "y"], how="outer",
                                  suffixes=("_ref", "_cand"))
    dr = dv["concentration_ref"].to_numpy()
    dc = dv["concentration_cand"].to_numpy()
    bad = ~(np.abs(dc - dr) <= REL_TOL * np.abs(dr))     # NaN (missing receptor) counts as fail
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(dr != 0, np.abs(dc - dr) / np.abs(dr), np.where(dc == dr, 0.0, np.inf))
    result.h4h_n_receptors = len(dv)
    result.h4h_max_rel_diff = float(np.nanmax(rel)) if len(rel) else 0.0
    result.h4h_n_fail = int(bad.sum())
    result.h4h_ok = result.h4h_n_fail == 0
    return result


def read_obukhov(sfc: Path | str) -> pd.Series:
    """YYMMDDHH (str) -> Monin-Obukhov length L (m) from an AERMET .sfc file."""
    out = {}
    with open(sfc, errors="replace") as f:
        next(f)
        for line in f:
            t = line.split()
            if len(t) < 12:
                continue
            yy, mo, dy, hr = int(t[0]) % 100, int(t[1]), int(t[2]), int(t[4])
            out[f"{yy:02d}{mo:02d}{dy:02d}{hr:02d}"] = float(t[11])
    return pd.Series(out, name="L")


def stability_split(ref: pd.DataFrame, cand: pd.DataFrame, sfc: Path | str) -> dict:
    L = read_obukhov(sfc)
    paired, _, _ = pair(ref, cand)
    case_max = float(ref["concentration"].max()) if len(ref) else 0.0
    lvals = paired["date"].astype(str).map(L)
    out = {}
    for label, mask in (("stable", lvals > 0), ("convective", lvals < 0)):
        sub = paired[mask.to_numpy()]
        m = strict_metrics(sub, 0, 0, case_max)
        out[label] = {
            "n_hours": int(sub["date"].nunique()),
            "n_values": m.n_paired,
            "zero_agreement": m.zero_agreement,
            "p99_rel_err": m.p99_rel_err,
            "pass_rate": m.frac_within_tol,
            "passes": m.zero_ok and m.p99_ok,
        }
    return out


def compare_case(candidate: Path | str, oracle: Path | str, *, epa: Path | str | None = None,
                 sfc: Path | str | None = None, case: str = "") -> CaseComparison:
    """Judge ``candidate`` against our binary's ``oracle`` (and EPA's file if given)."""
    epa_ref = Path(epa) if epa else Path(oracle)
    score = score_postfile_pair(epa_ref, candidate, case=case)
    epa_result = EpaResult(
        against="EPA reference POSTFILE" if epa else "our binary (case has no EPA POSTFILE)",
        n_paired=score.n_paired,
        slope=score.slope,
        max_abs_error=score.max_abs_error,
        passes=score.n_paired > 0 and score.passes(SLOPE_TOL),
    )
    ref_df, cand_df = load(oracle), load(candidate)
    result = CaseComparison(case, epa_result, strict_compare(ref_df, cand_df))
    if sfc:
        result.by_stability = stability_split(ref_df, cand_df, sfc)
    return result


def _case_paths(name: str, who: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cases as catalog

    case = catalog.get(name)
    manifest = case.manifest()
    return {
        "candidate": case.postfile(who),
        "oracle": case.postfile("ref"),
        "epa": case.epa_ref,
        "sfc": catalog.EPA_DIR / manifest["met"][0],
        "case": case.name,
    }


def format_row(c: CaseComparison) -> str:
    s = c.strict
    stab = c.by_stability
    split = " ".join(
        f"{k[:4]} {v['pass_rate']*100:6.2f}%({v['n_hours']}h)" for k, v in stab.items()
    )
    return (f"{c.case:20s} {'PASS' if c.passes else 'FAIL'}  slope {c.epa.slope:.6f} "
            f"[{'ok' if c.epa.passes else 'x'}]  zero {s.zero_agreement*100:7.3f}%  "
            f"p99 {s.p99_rel_err:.2e}  H4H fail {s.h4h_n_fail}/{s.h4h_n_receptors}  {split}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidate", type=Path)
    ap.add_argument("--oracle", type=Path, help="our compiled binary's POSTFILE")
    ap.add_argument("--epa", type=Path, help="EPA reference POSTFILE (EPA rule only)")
    ap.add_argument("--sfc", type=Path, help="AERMET .sfc file for the stability split")
    ap.add_argument("--case", action="append", default=[],
                    help="resolve paths from harness/cases.py (repeatable)")
    ap.add_argument("--who", default="port", help="candidate run under out/<who>/ (with --case)")
    ap.add_argument("--json", type=Path, help="write results as JSON")
    args = ap.parse_args()

    jobs = [_case_paths(n, args.who) for n in args.case]
    if args.candidate:
        if not args.oracle:
            ap.error("--candidate needs --oracle")
        jobs.append({"candidate": args.candidate, "oracle": args.oracle, "epa": args.epa,
                     "sfc": args.sfc, "case": args.candidate.parent.name})
    if not jobs:
        ap.error("give --case NAME or --candidate/--oracle")

    results = []
    for job in jobs:
        res = compare_case(**job)
        results.append(res)
        print(format_row(res))
    if args.json:
        args.json.write_text(json.dumps([r.to_dict() for r in results], indent=2))
    return 0 if all(r.passes for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
