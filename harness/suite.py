#!/usr/bin/env python3
"""Run cases through the reference binary and/or judge a candidate, as one table.

  python harness/suite.py --oracles          # (re)build out/ref/* with our binary
  python harness/suite.py --who ref2         # rerun the binary as a candidate: ref-vs-ref
  python harness/suite.py --who port         # judge the port (out/port/* from run_port.py)
  python harness/suite.py --vs-epa           # our binary vs EPA's shipped POSTFILEs

Writes out/suite_<who>.json (read by server.py's Proof screen).
``--write-checksums`` records sha256 of the data rows of every oracle POSTFILE
in cases/oracle_checksums.sha256 so another machine can check its build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cases as catalog  # noqa: E402
import compare  # noqa: E402
import run_ref  # noqa: E402

CHECKSUMS = catalog.CASES_DIR / "oracle_checksums.sha256"


def data_sha256(postfile: Path) -> str:
    """Hash of the POSTFILE without its '*' header (which carries run date/time)."""
    h = hashlib.sha256()
    with open(postfile, "rb") as f:
        for line in f:
            if not line.startswith(b"*"):
                h.update(line)
    return h.hexdigest()


def select(args) -> list[catalog.Case]:
    if args.case:
        return [catalog.get(n) for n in args.case]
    if args.tier in ("A", "B"):
        return catalog.tier_cases(args.tier)
    return list(catalog.CASES)


def vs_epa(case: catalog.Case) -> dict:
    """How far our binary's POSTFILE is from EPA's shipped one (informational)."""
    ref, ours = compare.load(case.epa_ref), compare.load(case.postfile("ref"))
    paired, ref_only, ours_only = compare.pair(ref, ours)
    r = paired["concentration_ref"].to_numpy()
    o = paired["concentration_cand"].to_numpy()
    d = np.abs(o - r)
    score = compare.score_postfile_pair(case.epa_ref, case.postfile("ref"), case=case.name)
    strict = compare.strict_compare(ref, ours)
    return {
        "case": case.name, "tier": case.tier, "n_values": int(len(r)),
        "n_differ": int((d > 0).sum()), "max_abs_diff": float(d.max()) if len(d) else 0.0,
        "epa_slope": score.slope, "epa_pass": bool(score.passes()),
        "strict_vs_epa_pass": strict.passes, "missing_rows": ref_only + ours_only,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", action="append", help="limit to these cases (repeatable)")
    ap.add_argument("--tier", choices=["A", "B", "all"], default="all",
                    help="A, B (includes A), or all (includes the holdout)")
    ap.add_argument("--oracles", action="store_true", help="run the binary into out/ref first")
    ap.add_argument("--who", help="candidate under out/<who>/; 'ref2' reruns the binary there")
    ap.add_argument("--vs-epa", action="store_true", help="table of our binary vs EPA's files")
    ap.add_argument("--write-checksums", action="store_true")
    ap.add_argument("--check-checksums", action="store_true")
    args = ap.parse_args()
    selected = select(args)
    status = 0

    if args.oracles:
        for case in selected:
            run = run_ref.run_case(case, who="ref")
            print(f"oracle {case.name:20s} {run.seconds:6.1f}s")

    if args.write_checksums or args.check_checksums:
        current = {c.name: data_sha256(c.postfile("ref")) for c in catalog.CASES}
        if args.write_checksums:
            CHECKSUMS.write_text("".join(f"{d}  {n}\n" for n, d in current.items()))
            print(f"wrote {CHECKSUMS}")
        else:
            expected = dict(reversed(line.split()) for line in CHECKSUMS.read_text().splitlines())
            for name, digest in current.items():
                ok = expected.get(name) == digest
                status |= not ok
                print(f"{'same' if ok else 'DIFFERENT'}  {name}")

    if args.vs_epa:
        rows = [vs_epa(c) for c in selected if c.epa_ref]
        print(f"\n{'case':20s} tier     values   differ   max|diff|   EPA slope  EPA  strict-vs-EPA")
        for r in rows:
            print(f"{r['case']:20s} {r['tier']:7s} {r['n_values']:8d} {r['n_differ']:8d} "
                  f"{r['max_abs_diff']:10.5f}  {r['epa_slope']:.6f}  "
                  f"{'pass' if r['epa_pass'] else 'FAIL'}  {'pass' if r['strict_vs_epa_pass'] else 'fail'}")
        (catalog.OUT_DIR / "suite_vs_epa.json").write_text(json.dumps(rows, indent=2))

    if args.who:
        results = []
        for case in selected:
            if args.who == "ref2":
                run_ref.run_case(case, who="ref2")
            cand = case.postfile(args.who)
            if not cand.exists():
                results.append({"case": case.name, "tier": case.tier, "passes": False,
                                "error": f"missing {cand.relative_to(catalog.ROOT)}"})
                print(f"{case.name:20s} MISSING {cand.relative_to(catalog.ROOT)}")
                continue
            res = compare.compare_case(cand, case.postfile("ref"), epa=case.epa_ref,
                                       sfc=catalog.EPA_DIR / case.manifest()["met"][0],
                                       case=case.name)
            print(compare.format_row(res))
            results.append({"tier": case.tier, **res.to_dict()})
        report = {
            "who": args.who,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "compare_sha256": hashlib.sha256(Path(compare.__file__).read_bytes()).hexdigest(),
            "results": results,
        }
        (catalog.OUT_DIR / f"suite_{args.who}.json").write_text(json.dumps(report, indent=2))
        n_pass = sum(r["passes"] for r in results)
        print(f"\n{n_pass}/{len(results)} cases pass")
        status |= n_pass != len(results)
    return status


if __name__ == "__main__":
    sys.exit(main())
