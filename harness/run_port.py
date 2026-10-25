#!/usr/bin/env python3
"""Run the generated Python port (port/aermod_py) on cases.

For each case: stage case.inp and its met/include files into out/<who>/<case>/
(as run_ref.py does), build the inputs with harness/glue.py, call

    aermod_py.run_case(project, met, setup, debug=...) -> glue.Result

check the result's shape and dates, and write postfile.pst in AERMOD's format.
With ``--debug`` the port's debug rows are pickled to port_debug.pkl for
harness/debugdiff.py. Failures write the traceback to error.txt and are
reported per case; the exit status is non-zero if any case failed.
"""

from __future__ import annotations

import argparse
import importlib
import pickle
import sys
import time
import traceback
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cases as catalog  # noqa: E402
import glue  # noqa: E402
import run_ref  # noqa: E402

PORT_DIR = catalog.ROOT / "port" / "aermod_py"
DEBUG_FILE = "port_debug.pkl"
ERROR_FILE = "error.txt"


@dataclass
class PortRun:
    case: str
    workdir: Path
    ok: bool
    seconds: float
    error: str = ""


def load_port(package_dir: Path = PORT_DIR):
    """Import the package at package_dir fresh (the repair loop rewrites it between runs)."""
    package_dir = Path(package_dir).resolve()
    if not (package_dir / "__init__.py").exists():
        raise ImportError(f"{package_dir} has no __init__.py; the port has not been generated")
    package, parent = package_dir.name, str(package_dir.parent)
    for name in [m for m in sys.modules if m == package or m.startswith(package + ".")]:
        del sys.modules[name]
    sys.path.insert(0, parent)
    try:
        importlib.invalidate_caches()
        module = importlib.import_module(package)
    finally:
        sys.path.remove(parent)
    if Path(module.__file__).resolve().parent != package_dir:
        raise ImportError(f"imported {module.__file__}, not {package_dir}")
    if not callable(getattr(module, "run_case", None)):
        raise ImportError(f"{package_dir} has no run_case(); see prompts/contract.md")
    return module


def check_result(result: object, project: glue.Project, met: glue.Met) -> glue.Result:
    """Reject anything that is not a well-formed Result for this case."""
    for attr in ("dates", "conc"):
        if not hasattr(result, attr):
            raise TypeError(f"run_case returned {type(result).__name__} without .{attr}")
    dates = np.asarray(result.dates)
    conc = np.asarray(result.conc)
    want = glue.expected_dates(project, met)
    if dates.shape != want.shape or not np.array_equal(dates.astype(np.int64), want):
        bad = next((i for i, (a, b) in enumerate(zip(dates, want)) if a != b), min(len(dates), len(want)))
        raise ValueError(f"dates differ from the met file inside STARTEND at hour index {bad} "
                         f"({len(dates)} returned, {len(want)} expected)")
    if conc.shape != (len(want), len(project.receptors)):
        raise ValueError(f"conc shape {conc.shape}, expected {(len(want), len(project.receptors))}")
    if conc.dtype != np.float64:
        raise TypeError(f"conc dtype {conc.dtype}, expected float64")
    if not np.all(np.isfinite(conc)):
        raise ValueError(f"{int((~np.isfinite(conc)).sum())} non-finite concentrations")
    return glue.Result(dates=want, conc=conc, debug=list(getattr(result, "debug", []) or []))


def run_case(case: catalog.Case, *, debug: bool = False, who: str = "port",
             package_dir: Path = PORT_DIR) -> PortRun:
    workdir = case.out_dir(who)
    t0 = time.monotonic()
    try:
        inp = run_ref.stage(case.inp.read_text(), run_ref.case_files(case), workdir)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            project = glue.load_project(inp)
        met = glue.load_met(project, workdir)
        setup = glue.setup_values(project, met)
        port = load_port(package_dir)
        result = check_result(port.run_case(project, met, setup, debug=debug), project, met)
        glue.write_postfile(workdir / catalog.POSTFILE_NAME, project, result.dates, result.conc)
        if debug:
            with open(workdir / DEBUG_FILE, "wb") as f:
                pickle.dump(result.debug, f)
    except Exception:
        err = traceback.format_exc()
        if workdir.exists():
            (workdir / ERROR_FILE).write_text(err)
        return PortRun(case.name, workdir, False, time.monotonic() - t0, err)
    return PortRun(case.name, workdir, True, time.monotonic() - t0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cases", nargs="*", help="case names (see harness/cases.py)")
    ap.add_argument("--tier", choices=["A", "B"], help="all cases of a tier (B includes A)")
    ap.add_argument("--all", action="store_true", help="every case, including the holdout")
    ap.add_argument("--debug", action="store_true", help="also save the port's debug rows")
    ap.add_argument("--who", help="output subdirectory under out/ (default port or port_debug)")
    ap.add_argument("--package", type=Path, default=PORT_DIR,
                    help="package directory to import (default port/aermod_py)")
    args = ap.parse_args()

    if args.all:
        selected = list(catalog.CASES)
    elif args.tier:
        selected = catalog.tier_cases(args.tier)
    else:
        selected = [catalog.get(n) for n in args.cases]
    if not selected:
        ap.error("name at least one case, or use --tier/--all")
    who = args.who or ("port_debug" if args.debug else "port")

    failed = 0
    for case in selected:
        run = run_case(case, debug=args.debug, who=who, package_dir=args.package)
        if run.ok:
            print(f"ok   {case.name:20s} {run.seconds:7.1f}s  "
                  f"{(run.workdir / catalog.POSTFILE_NAME).relative_to(catalog.ROOT)}")
        else:
            failed += 1
            last = run.error.strip().splitlines()[-1] if run.error.strip() else "?"
            print(f"FAIL {case.name:20s} {last}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
