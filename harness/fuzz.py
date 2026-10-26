#!/usr/bin/env python3
"""Random in-scope decks, run through our binary, the glue and (optionally) the port.

    python harness/fuzz.py -n 20 --seed 1            # binary + glue checks
    python harness/fuzz.py -n 20 --seed 1 --tier B   # some sources get PRIME buildings
    python harness/fuzz.py -n 20 --port port/aermod_py   # also score the port

Each deck has 1-3 POINT sources with random stack parameters (some at ambient
exit temperature, some with HROFDY/SEASON/MONTH emission factors), polar and
discrete receptors, and the real met of an existing case (AERTEST's 96 hours
by default). For every deck:

* our binary must run it (it is the oracle; out/fuzz/<deck>/ref);
* ``glue.setup_values`` must equal the SETUP.DMP that ref/aermod_dump writes,
  bit for bit (skipped if ref/aermod_dump is missing);
* ``glue.write_postfile`` fed the binary's concentrations must reproduce the
  binary's POSTFILE data rows byte for byte (receptor expansion and format);
* with ``--port``, the port's POSTFILE must pass harness/compare.py against the
  binary's (the EPA rule's reference is the binary too: there is no EPA file).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cases as catalog  # noqa: E402
import compare  # noqa: E402
import glue  # noqa: E402
import run_port  # noqa: E402
import run_ref  # noqa: E402
import setup_inputs  # noqa: E402

DUMP_BINARY = catalog.ROOT / "ref" / "aermod_dump"
FUZZ_DIR = catalog.OUT_DIR / "fuzz"
EMISFACT_CHOICES = {"HROFDY": 24, "SEASON": 4, "MONTH": 12}


def _f(x: float) -> str:
    return f"{x:.2f}"


def make_deck(rng: random.Random, tier: str, met: tuple[str, str]) -> str:
    n_src = rng.randint(1, 3)
    so = ["SO STARTING", "   ELEVUNIT  METERS"]
    for i in range(1, n_src + 1):
        sid = f"STK{i}"
        x, y = rng.uniform(-300, 300), rng.uniform(-300, 300)
        temp = 0.0 if rng.random() < 0.15 else rng.uniform(300, 600)
        so.append(f"   LOCATION  {sid}  POINT  {_f(x)}  {_f(y)}  0.0")
        so.append(f"   SRCPARAM  {sid}  {_f(rng.uniform(1, 500))}  {_f(rng.uniform(5, 150))}  "
                  f"{_f(temp)}  {_f(rng.uniform(0.5, 30))}  {_f(rng.uniform(0.3, 6))}")
        if tier == "B" and rng.random() < 0.6:
            base_h, base_w, base_l = rng.uniform(10, 60), rng.uniform(20, 120), rng.uniform(20, 120)
            for key, base, amp in (("BUILDHGT", base_h, 0.0), ("BUILDWID", base_w, 0.4),
                                   ("BUILDLEN", base_l, 0.4), ("XBADJ", -base_l / 2, 0.8),
                                   ("YBADJ", 0.0, 20.0)):
                vals = [base + (amp * base if key in ("BUILDWID", "BUILDLEN") else amp)
                        * math.sin(math.radians(10 * (k + 1))) for k in range(36)]
                for row in range(0, 36, 6):
                    # AERMOD reads the keyword from columns 4-11, so pad it to 8 characters.
                    so.append(f"   {key:<8s}  {sid}  " + "  ".join(_f(v) for v in vals[row:row + 6]))
        if rng.random() < 0.3:
            qflag = rng.choice(sorted(EMISFACT_CHOICES))
            vals = [rng.uniform(0.0, 2.0) for _ in range(EMISFACT_CHOICES[qflag])]
            for row in range(0, len(vals), 12):
                so.append(f"   EMISFACT  {sid}  {qflag}  " + "  ".join(_f(v) for v in vals[row:row + 12]))
    so += ["   SRCGROUP  ALL", "SO FINISHED"]

    rings = sorted(rng.sample([50, 100, 175, 250, 350, 500, 750, 1000, 1500, 2000], rng.randint(2, 4)))
    re_ = ["RE STARTING", "   GRIDPOLR POL1 STA", "                 ORIG STK1",
           "                 DIST " + " ".join(f"{d}." for d in rings),
           f"                 GDIR {rng.choice([12, 18, 36])} {rng.choice([10, 20, 30])} 10",
           "   GRIDPOLR POL1 END"]
    for _ in range(rng.randint(0, 8)):
        re_.append(f"   DISCCART  {_f(rng.uniform(-1500, 1500))}  {_f(rng.uniform(-1500, 1500))}")
    re_.append("RE FINISHED")

    return "\n".join([
        "CO STARTING", "   TITLEONE  Fuzz deck", "   MODELOPT  CONC  FLAT", "   AVERTIME  1",
        "   POLLUTID  OTHER", "   RUNORNOT  RUN", "   ERRORFIL  errors.out", "CO FINISHED", "",
        *so, "", *re_, "",
        "ME STARTING", f"   SURFFILE  {Path(met[0]).name}", f"   PROFFILE  {Path(met[1]).name}",
        "   SURFDATA  14735  1988  ALBANY,NY", "   UAIRDATA  14735  1988  ALBANY,NY",
        "   PROFBASE  0.0  METERS", "ME FINISHED", "",
        "OU STARTING", f"   POSTFILE  1  ALL  PLOT  {catalog.POSTFILE_NAME}", "OU FINISHED", "",
    ])


def postfile_rows(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip() and not line.startswith("*")]


@dataclass
class FuzzResult:
    deck: str
    ok: bool
    problems: list[str] = field(default_factory=list)
    port: str = ""


def check_deck(name: str, text: str, staged: list[Path], *, dump: bool,
               port_dir: Path | None) -> FuzzResult:
    res = FuzzResult(name, True)
    base = FUZZ_DIR / name
    try:
        ref = run_ref.run_deck(text, staged, base / "ref")
    except RuntimeError as exc:
        return FuzzResult(name, False, [f"binary failed: {str(exc).splitlines()[0]}"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        project = glue.load_project(base / "ref" / "case.inp")
    met = glue.load_met(project, base / "ref")
    values = glue.setup_values(project, met)

    rows = postfile_rows(ref.postfile)
    nrec = len(project.receptors)
    conc = np.array([float(r.split()[2]) for r in rows]).reshape(-1, nrec)
    dates = glue.expected_dates(project, met)
    roundtrip = base / "glue_roundtrip.pst"
    glue.write_postfile(roundtrip, project, dates, conc)
    if postfile_rows(roundtrip) != rows:
        res.problems.append("glue POSTFILE round trip differs from the binary's")

    if dump:
        run_ref.run_deck(text, staged, base / "dump", binary=DUMP_BINARY)
        diffs = setup_inputs.compare_dump(values, setup_inputs.read_dump(base / "dump" / "SETUP.DMP"),
                                          glue.SETUP_SCRATCH)
        res.problems += [f"setup {d}" for d in diffs]

    if port_dir is not None:
        inp = run_ref.stage(text, staged, base / "port")
        run = run_port.run_staged(inp, package_dir=port_dir, name=name)
        if not run.ok:
            res.port = "CRASH " + run.error.strip().splitlines()[-1]
            res.problems.append("port crashed")
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cmp = compare.compare_case(base / "port" / catalog.POSTFILE_NAME, ref.postfile,
                                           case=name)
            res.port = compare.format_row(cmp)
            if not cmp.passes:
                res.problems.append("port fails compare.py")
    res.ok = not res.problems
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=10, help="number of decks")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tier", choices=["A", "B"], default="A")
    ap.add_argument("--met-case", default="AERTEST", help="case whose met files the decks use")
    ap.add_argument("--port", type=Path, help="also run and score this port package directory")
    ap.add_argument("--no-dump", action="store_true", help="skip the SETUP.DMP comparison")
    args = ap.parse_args()

    met_case = catalog.get(args.met_case)
    staged = run_ref.case_files(met_case)
    met = tuple(met_case.manifest()["met"])
    dump = not args.no_dump and DUMP_BINARY.exists()
    if not dump and not args.no_dump:
        print(f"note: {DUMP_BINARY.relative_to(catalog.ROOT)} missing (ref/build_dump.sh); "
              "skipping the SETUP.DMP comparison", file=sys.stderr)
    rng = random.Random(args.seed)
    results = []
    for i in range(args.n):
        name = f"{args.tier}_{args.seed}_{i:03d}"
        text = make_deck(rng, args.tier, met)
        res = check_deck(name, text, staged, dump=dump, port_dir=args.port)
        results.append(res)
        print(f"{'ok  ' if res.ok else 'FAIL'} {name}  {'; '.join(res.problems[:3])}")
        if res.port:
            print(f"      {res.port}")
    FUZZ_DIR.mkdir(parents=True, exist_ok=True)
    (FUZZ_DIR / f"summary_{args.tier}_{args.seed}.json").write_text(
        json.dumps([asdict(r) for r in results], indent=1) + "\n")
    bad = sum(not r.ok for r in results)
    print(f"{len(results) - bad}/{len(results)} decks ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
