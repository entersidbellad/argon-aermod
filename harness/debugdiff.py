#!/usr/bin/env python3
"""Find where the port's intermediate values first leave AERMOD's.

Reference records come from the DEBUGOPT files of ``run_ref.py --debug``
(out/ref_debug/<case>/, parsed by harness/dbgparse.py). Port records come from
the ``debug`` rows of the port's Result, pickled by ``run_port.py --debug``
(out/port_debug/<case>/port_debug.pkl): (KURDAT, ISRC, IREC, comp, sub, var,
value), keyed and numbered exactly like dbgparse records.

Walking the reference in the order AERMOD computed it, the report gives the
first record whose port value differs by more than one unit in the last digit
AERMOD printed, the first record the port did not emit, which catalogued
variables the port never emits, and which names it emits that are not in
prompts/debug_vars.md. Exit status 0 means every reference record was matched.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cases as catalog  # noqa: E402
import dbgparse  # noqa: E402

CATALOG = Path(__file__).resolve().parent / "debug_vars.json"
DEBUG_FILE = "port_debug.pkl"


def known_names() -> set[tuple[str, str, str]]:
    """(sub, comp, var) of every variable in harness/debug_vars.json."""
    return {(v["sub"], v["comp"], v["var"]) for v in json.loads(CATALOG.read_text())}


def port_records(rows: list[tuple]) -> list[dbgparse.Record]:
    """Number the port's rows like dbgparse does; the port's tolerance is unused."""
    raw = []
    for i, row in enumerate(rows):
        if len(row) != 7:
            raise ValueError(f"debug row {i} has {len(row)} fields, expected "
                             "(KURDAT, ISRC, IREC, comp, sub, var, value): {row!r}")
        date, isrc, irec, comp, sub, var, value = row
        raw.append((int(date), int(isrc), int(irec), str(comp), str(sub), str(var),
                    float(value), 0.0))
    return dbgparse.assemble((0, raw))


@dataclass
class Point:
    seq: int                # position in AERMOD's order
    key: tuple
    ref: float
    port: float | None
    tol: float

    def line(self) -> str:
        date, isrc, irec, comp, sub, var, k = self.key
        where = f"{sub}{'/' + comp if comp else ''} {var}[{k}] date={date} isrc={isrc} irec={irec}"
        if self.port is None:
            return f"{where}: AERMOD printed {self.ref:.9g}, port emitted nothing"
        return (f"{where}: AERMOD {self.ref:.9g}, port {self.port:.9g} "
                f"(|diff| {abs(self.port - self.ref):.3g} > tol {self.tol:.3g})")


@dataclass
class Report:
    case: str
    n_ref: int
    n_port: int
    n_matched: int
    n_divergent: int
    n_missing: int
    n_extra: int
    first_divergent: Point | None
    first_missing: Point | None
    divergent_by_var: dict[str, int] = field(default_factory=dict)
    missing_by_var: dict[str, int] = field(default_factory=dict)
    never_emitted: list[str] = field(default_factory=list)
    unknown_names: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.n_divergent == 0 and self.n_missing == 0 and not self.unknown_names

    @property
    def first_problem(self) -> Point | None:
        """Whichever of first_divergent / first_missing AERMOD reached first."""
        points = [p for p in (self.first_divergent, self.first_missing) if p is not None]
        return min(points, key=lambda p: p.seq) if points else None

    def text(self, top: int = 10) -> str:
        out = [f"{self.case}: {self.n_matched}/{self.n_ref} AERMOD records matched, "
               f"{self.n_divergent} divergent, {self.n_missing} not emitted; "
               f"{self.n_port} port rows ({self.n_extra} with no AERMOD counterpart)"]
        if self.first_problem is not None:
            out.append("first problem in AERMOD's order: " + self.first_problem.line())
        if self.first_divergent is not None and self.first_divergent is not self.first_problem:
            out.append("first divergence: " + self.first_divergent.line())
        if self.first_missing is not None and self.first_missing is not self.first_problem:
            out.append("first missing: " + self.first_missing.line())
        for title, counts in (("divergent", self.divergent_by_var), ("missing", self.missing_by_var)):
            if counts:
                items = sorted(counts.items(), key=lambda kv: -kv[1])[:top]
                out.append(f"{title} by variable: " + ", ".join(f"{k} {n}" for k, n in items))
        if self.never_emitted:
            out.append("never emitted: " + ", ".join(self.never_emitted))
        if self.unknown_names:
            out.append("not in prompts/debug_vars.md: " + ", ".join(self.unknown_names))
        return "\n".join(out)


def _name(sub: str, comp: str, var: str) -> str:
    return f"{sub}{'/' + comp if comp else ''}.{var}"


def diff(ref: list[dbgparse.Record], port: list[dbgparse.Record], case: str = "",
         known: set[tuple[str, str, str]] | None = None) -> Report:
    by_key = {r.key: r for r in port}
    ref_keys = set()
    first_div = first_miss = None
    n_div = n_miss = 0
    div_by: Counter[str] = Counter()
    miss_by: Counter[str] = Counter()
    for seq, r in enumerate(ref):
        ref_keys.add(r.key)
        p = by_key.get(r.key)
        name = _name(r.sub, r.comp, r.var)
        if p is None:
            n_miss += 1
            miss_by[name] += 1
            first_miss = first_miss or Point(seq, r.key, r.value, None, r.tol)
        elif not math.isfinite(p.value) or abs(p.value - r.value) > r.tol:
            n_div += 1
            div_by[name] += 1
            first_div = first_div or Point(seq, r.key, r.value, p.value, r.tol)

    ref_names = {(r.sub, r.comp, r.var) for r in ref}
    port_names = {(p.sub, p.comp, p.var) for p in port}
    known = known_names() if known is None else known
    return Report(
        case=case, n_ref=len(ref), n_port=len(port),
        n_matched=len(ref) - n_miss - n_div, n_divergent=n_div, n_missing=n_miss,
        n_extra=sum(1 for p in port if p.key not in ref_keys),
        first_divergent=first_div, first_missing=first_miss,
        divergent_by_var=dict(div_by), missing_by_var=dict(miss_by),
        never_emitted=sorted(_name(*n) for n in ref_names - port_names),
        unknown_names=sorted(_name(*n) for n in port_names - known),
    )


def diff_case(case: catalog.Case, who: str = "port_debug", ref_who: str = "ref_debug") -> Report:
    ref = dbgparse.parse_dir(case.out_dir(ref_who))
    pkl = case.out_dir(who) / DEBUG_FILE
    if not pkl.exists():
        raise FileNotFoundError(f"{pkl} missing; run harness/run_port.py --debug {case.name}")
    with open(pkl, "rb") as f:
        rows = pickle.load(f)
    return diff(ref, port_records(rows), case.name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cases", nargs="+", help="case names with out/ref_debug/<case> (harness/cases.py)")
    ap.add_argument("--who", default="port_debug", help="port run under out/<who>/")
    ap.add_argument("--ref-who", default="ref_debug", help="reference run under out/<ref-who>/")
    ap.add_argument("--json", type=Path, help="write the reports as JSON")
    args = ap.parse_args()

    reports = []
    for name in args.cases:
        rep = diff_case(catalog.get(name), args.who, args.ref_who)
        reports.append(rep)
        print(rep.text())
    if args.json:
        args.json.write_text(json.dumps([asdict(r) for r in reports], indent=1))
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
