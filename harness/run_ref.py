#!/usr/bin/env python3
"""Run the compiled AERMOD reference binary on a case.

Each run stages case.inp plus its met/include files into out/<who>/<case>/ and
writes postfile.pst there. ``--debug`` adds ``CO DEBUGOPT MODEL METEOR [PRIME]``
so AERMOD also writes its intermediate-value debug files (PRIME only when the
deck has building data, since AERMOD rejects it otherwise).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cases as catalog  # noqa: E402

DEFAULT_BINARY = catalog.ROOT / "ref" / "aermod"
SUCCESS_BANNER = "AERMOD Finishes Successfully"
BUILDING_KEYWORDS = ("BUILDHGT", "BUILDWID", "BUILDLEN", "XBADJ", "YBADJ")


@dataclass
class RefRun:
    workdir: Path
    postfile: Path
    seconds: float
    debug_files: list[Path]


def has_buildings(inp_text: str) -> bool:
    return any(
        tok in BUILDING_KEYWORDS
        for line in inp_text.upper().splitlines()
        if not line.lstrip().startswith("**")
        for tok in line.split()[:2]
    )


def debug_options(inp_text: str) -> list[str]:
    return ["MODEL", "METEOR"] + (["PRIME"] if has_buildings(inp_text) else [])


def add_debugopt(inp_text: str) -> str:
    """Insert one DEBUGOPT record right after CO STARTING."""
    lines = inp_text.splitlines()
    for i, line in enumerate(lines):
        if line.split()[:2] == ["CO", "STARTING"]:
            lines.insert(i + 1, "   DEBUGOPT  " + "  ".join(debug_options(inp_text)))
            return "\n".join(lines) + "\n"
    raise ValueError("deck has no 'CO STARTING' record")


def run_deck(
    inp_text: str,
    staged: list[Path],
    workdir: Path,
    *,
    debug: bool = False,
    binary: Path = DEFAULT_BINARY,
    postfile_name: str = catalog.POSTFILE_NAME,
) -> RefRun:
    """Run AERMOD on deck text with the given files symlinked beside it."""
    binary = Path(binary).resolve()
    if not binary.exists():
        raise FileNotFoundError(f"{binary} missing; run ref/fetch.py and ref/build.sh")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    for f in staged:
        if not f.exists():
            raise FileNotFoundError(f"{f} missing; run ref/fetch.py")
        os.symlink(f.resolve(), workdir / f.name)
    (workdir / "case.inp").write_text(add_debugopt(inp_text) if debug else inp_text)

    t0 = time.monotonic()
    proc = subprocess.run(
        [str(binary), "case.inp", "case.out"], cwd=workdir,
        capture_output=True, text=True, errors="replace",
    )
    seconds = time.monotonic() - t0
    (workdir / "stdout.txt").write_text(proc.stdout + proc.stderr)
    out_text = (workdir / "case.out").read_text(errors="replace") if (workdir / "case.out").exists() else ""
    postfile = workdir / postfile_name
    if proc.returncode != 0 or SUCCESS_BANNER not in out_text + proc.stdout or not postfile.exists():
        errors = (workdir / "errors.out").read_text(errors="replace") if (workdir / "errors.out").exists() else ""
        raise RuntimeError(
            f"AERMOD failed in {workdir} (exit {proc.returncode}).\n"
            f"--- stdout tail ---\n{proc.stdout[-1500:]}\n--- errors.out ---\n{errors[-1500:]}"
        )
    debug_files = sorted(p for p in workdir.iterdir() if p.suffix.lower() == ".dbg")
    return RefRun(workdir, postfile, seconds, debug_files)


def case_files(case: catalog.Case) -> list[Path]:
    manifest = case.manifest()
    return [catalog.EPA_DIR / rel for rel in manifest["met"] + manifest["includes"]]


def run_case(case: catalog.Case, *, debug: bool = False, who: str | None = None,
             binary: Path = DEFAULT_BINARY) -> RefRun:
    who = who or ("ref_debug" if debug else "ref")
    return run_deck(case.inp.read_text(), case_files(case), case.out_dir(who),
                    debug=debug, binary=binary)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cases", nargs="*", help="case names (see harness/cases.py)")
    ap.add_argument("--tier", choices=["A", "B"], help="all cases of a tier (B includes A)")
    ap.add_argument("--all", action="store_true", help="every case, including the holdout")
    ap.add_argument("--debug", action="store_true", help="add CO DEBUGOPT MODEL METEOR [PRIME]")
    ap.add_argument("--who", help="output subdirectory under out/ (default ref or ref_debug)")
    ap.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    args = ap.parse_args()

    if args.all:
        selected = list(catalog.CASES)
    elif args.tier:
        selected = catalog.tier_cases(args.tier)
    else:
        selected = [catalog.get(n) for n in args.cases]
    if not selected:
        ap.error("name at least one case, or use --tier/--all")

    failed = 0
    for case in selected:
        try:
            run = run_case(case, debug=args.debug, who=args.who, binary=args.binary)
        except (RuntimeError, FileNotFoundError) as exc:
            failed += 1
            print(f"FAIL {case.name}: {exc}", file=sys.stderr)
            continue
        extra = f", debug: {', '.join(p.name for p in run.debug_files)}" if args.debug else ""
        print(f"ok   {case.name:20s} {run.seconds:7.1f}s  {run.postfile.relative_to(catalog.ROOT)}{extra}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
