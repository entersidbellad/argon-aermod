#!/usr/bin/env python3
"""Pack the in-scope AERMOD Fortran plus a subroutine index into one prompt.

Scope (see prompts/contract.md): modules.f whole (module state); every other
file (aermod.f, metext, iblval, siggrid, tempgrid, windgrid, calc1, calc2,
prise, sigmas, and prime.f for tier B) reduced to the program units reachable
from HRLOOP (plus the PRIME1/NUMPR1 initialisers for tier B) through CALL
statements and function references, minus the
branches in EXCLUDE_* (other source types, NO2 chemistry, deposition,
platform downwash, EVALFILE/events, hourly emission files, averaging and
output). Tier A also cuts the PRIME entry points.

Comments are kept by default; both counts (with comments, code only) are
reported. Writes context/tier_<T>.txt (gitignored: it is EPA source) and
context/index_tier_<T>.json + context/tokens.json (committed). Token counts
use Gemini count_tokens when GEMINI_API_KEY is set, else tiktoken o200k_base.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import tiktoken
from google import genai

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "ref" / "aermod_source" / "aermod_source_v26135"
CONTEXT = ROOT / "context"
MODEL = "gemini-4-argon"

WHOLE_FILES = ["modules.f"]
REDUCED_FILES = ["aermod.f", "metext.f", "iblval.f", "siggrid.f", "tempgrid.f", "windgrid.f",
                 "calc1.f", "calc2.f", "prise.f", "sigmas.f"]
TIER_B_FILES = ["prime.f"]
# NUMPR1/PRIME1 are called from the main program before HRLOOP and only set PRIME
# module constants; without them the port cannot know those values.
ROOTS = ["HRLOOP", "NUMPR1", "PRIME1"]

EXCLUDE_COMMON = {
    # other source types and their dispatch
    "ACALC", "VCALC", "OCALC", "LCALC", "RLCALC", "BL_CALC", "SWCALC", "ARISE", "AFLUXES",
    "PLAT_DOWNWASH", "AIRCRAFT", "AHRQREAD",
    # NO2 / chemistry options
    "ARM2_CALC", "OLM_CALC", "PVMRM_CALC", "GRSM_CALC", "TTRM_CALC", "OZONVALS", "VARYNOXVALS",
    "O3EXT", "NOXEXT",
    # background, hourly emission files
    "BGEXT", "BGVAL", "SUMBACK", "HRQREAD", "HRQEXT",
    # deposition and plume depletion
    "VDP", "SCAVRAT", "PRM_PDEP", "PRM_PDEPG", "PDEP", "PDEPG", "DEPLETE", "QATR2", "QG2D2",
    # platform downwash
    "PLAT_GRADPLUMADJ", "PLAT_CUBIC",
    # EVALFILE / event processing
    "EVALCK", "EVALFL", "EVLINI", "EV_SUMVAL",
    # averaging, ranking and output (done by the glue layer / pyaermod)
    "AVER", "HIVALS", "MAXFIL", "MXDLYFL", "POSTFL", "PRTDAY", "RSDUMP", "TOXXFL",
    "METSUM", "CHK_ENDYR", "HEADER",
    # error/message handling (the port raises instead)
    "ERRHDL",
}
EXCLUDE_TIER_A = {"PRMCALC", "GAMCALC", "WAKE_INI"}

UNIT_RE = re.compile(
    r"^ {6,}(?:RECURSIVE +)?(?:(?:DOUBLE PRECISION|INTEGER|LOGICAL|REAL(?:\*\d)?|CHARACTER\*?\d*) +)?"
    r"(SUBROUTINE|FUNCTION|MODULE|PROGRAM|BLOCK DATA) +([A-Z][A-Z0-9_]*)", re.I)
CALL_RE = re.compile(r"\bCALL\s+([A-Z][A-Z0-9_]*)", re.I)


@dataclass
class Unit:
    name: str
    kind: str
    file: str
    start: int                     # 1-based first line
    end: int                       # 1-based last line
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    tokens: int = 0


def is_comment(line: str) -> bool:
    return line[:1] in ("C", "c", "*", "!") or line.lstrip().startswith("!")


def scan_file(path: Path) -> list[Unit]:
    lines = path.read_text(encoding="latin-1").split("\n")
    heads = []
    for i, line in enumerate(lines):
        if is_comment(line) or re.match(r"^\s+END\b", line, re.I):
            continue
        m = UNIT_RE.match(line)
        if m and "MODULE PROCEDURE" not in line.upper():
            heads.append((i, m.group(1).upper(), m.group(2).upper()))
    units = []
    for n, (i, kind, name) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        units.append(Unit(name, kind, path.name, i + 1, end))
    return units


def unit_text(unit: Unit, cache: dict[str, list[str]], strip_comments: bool = False) -> str:
    lines = cache.setdefault(unit.file, (SRC / unit.file).read_text(encoding="latin-1").split("\n"))
    body = lines[unit.start - 1:unit.end]
    if strip_comments:
        body = [ln for ln in body if ln.strip() and not is_comment(ln)]
    return "\n".join(body)


def build_index(files: list[str]) -> dict[str, Unit]:
    index: dict[str, Unit] = {}
    for f in files:
        for u in scan_file(SRC / f):
            index.setdefault(u.name, u)   # first definition wins (internal EXPATH copies)
    cache: dict[str, list[str]] = {}
    function_names = {n for n, u in index.items() if u.kind == "FUNCTION"}
    fn_re = re.compile(r"\b(" + "|".join(sorted(function_names)) + r")\s*\(", re.I) \
        if function_names else None
    for u in index.values():
        code = [ln for ln in unit_text(u, cache).split("\n")[1:] if not is_comment(ln)]
        found = {c.upper() for ln in code for c in CALL_RE.findall(ln)}
        if fn_re:
            found |= {c.upper() for ln in code for c in fn_re.findall(ln)} - {u.name}
        u.calls = sorted(c for c in found if c in index)
    return index


def reachable(index: dict[str, Unit], exclude: set[str]) -> set[str]:
    seen: set[str] = set()
    stack = [r for r in ROOTS if r in index]
    while stack:
        name = stack.pop()
        if name in seen or name in exclude:
            continue
        seen.add(name)
        stack += index[name].calls
    return seen


def select_units(tier: str) -> tuple[list[Unit], dict[str, Unit]]:
    files = WHOLE_FILES + REDUCED_FILES + (TIER_B_FILES if tier == "B" else [])
    index = build_index(files)
    exclude = EXCLUDE_COMMON | (EXCLUDE_TIER_A if tier == "A" else set())
    keep = reachable(index, exclude)
    keep |= {u.name for u in index.values() if u.file in WHOLE_FILES}
    selected = [index[n] for n in keep]
    order = {f: i for i, f in enumerate(files)}
    selected.sort(key=lambda u: (order[u.file], u.start))
    names = {u.name for u in selected}
    for u in selected:
        u.calls = [c for c in u.calls if c in names]
    for u in selected:
        for c in u.calls:
            index[c].called_by.append(u.name)
    return selected, index


class TokenCounter:
    def __init__(self) -> None:
        self.method = "tiktoken o200k_base (proxy)"
        self._client = None
        if os.environ.get("GEMINI_API_KEY"):
            self._client = genai.Client()
            self.method = f"Gemini count_tokens ({MODEL})"
        else:
            self._enc = tiktoken.get_encoding("o200k_base")

    def __call__(self, text: str) -> int:
        if self._client is not None:
            return int(self._client.models.count_tokens(model=MODEL, contents=text).total_tokens)
        return len(self._enc.encode(text, disallowed_special=()))


def render(tier: str, units: list[Unit], strip_comments: bool = False) -> str:
    cache: dict[str, list[str]] = {}
    out = [f"AERMOD 26135 Fortran, tier {tier} scope ({len(units)} program units"
           f"{', comment lines removed' if strip_comments else ''}).",
           "", "SUBROUTINE INDEX (name, file:lines, calls)"]
    for u in units:
        out.append(f"  {u.name:14s} {u.file}:{u.start}-{u.end}  calls: {', '.join(u.calls) or '-'}")
    current = None
    for u in units:
        if u.file != current:
            current = u.file
            out += ["", f"##### FORTRAN FILE {u.file}"]
        out += [f"##### UNIT {u.name} ({u.kind}) {u.file}:{u.start}-{u.end}",
                unit_text(u, cache, strip_comments)]
    return "\n".join(out) + "\n"


def load_index(tier: str) -> dict[str, dict]:
    """name -> unit record from context/index_tier_<T>.json."""
    path = CONTEXT / f"index_tier_{tier}.json"
    return {u["name"]: u for u in json.loads(path.read_text())}


def fortran_unit(name: str, tier: str = "B") -> str:
    """Source text of one program unit, located through the committed index."""
    rec = load_index(tier)[name.upper()]
    lines = (SRC / rec["file"]).read_text(encoding="latin-1").split("\n")
    return "\n".join(lines[rec["start"] - 1:rec["end"]])


def pack(tier: str, counter: TokenCounter | None = None, strip_comments: bool = False) -> dict:
    units, _ = select_units(tier)
    counter = counter or TokenCounter()
    cache: dict[str, list[str]] = {}
    per_file: dict[str, int] = {}
    for u in units:
        u.tokens = counter(unit_text(u, cache))
        per_file[u.file] = per_file.get(u.file, 0) + u.tokens
    text = render(tier, units, strip_comments)
    CONTEXT.mkdir(exist_ok=True)
    (CONTEXT / f"tier_{tier}.txt").write_text(text)
    (CONTEXT / f"index_tier_{tier}.json").write_text(
        json.dumps([asdict(u) for u in units], indent=1) + "\n")
    with_comments = text if not strip_comments else render(tier, units)
    code_only = text if strip_comments else render(tier, units, strip_comments=True)
    return {
        "tier": tier,
        "method": counter.method,
        "packed": "code only" if strip_comments else "with comments",
        "tokens_with_comments": counter(with_comments),
        "tokens_code_only": counter(code_only),
        "units": len(units),
        "lines": sum(u.end - u.start + 1 for u in units),
        "per_file_tokens_with_comments": per_file,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", choices=["A", "B", "both"], default="both")
    ap.add_argument("--strip-comments", action="store_true",
                    help="pack code lines only (Fortran comment and blank lines removed)")
    args = ap.parse_args()
    if not SRC.exists():
        sys.exit(f"missing {SRC}; run ref/fetch.py first")
    counter = TokenCounter()
    tiers = ["A", "B"] if args.tier == "both" else [args.tier]
    report = {t: pack(t, counter, args.strip_comments) for t in tiers}
    print(f"token counts: {counter.method}")
    for t, r in report.items():
        print(f"tier {t}: {r['tokens_with_comments']:,} tokens with comments, "
              f"{r['tokens_code_only']:,} code only; {r['units']} units, {r['lines']:,} lines; "
              f"packed {r['packed']} -> context/tier_{t}.txt")
        for f, n in r["per_file_tokens_with_comments"].items():
            print(f"    {f:12s} {n:8,}")
    tokens_path = CONTEXT / "tokens.json"
    existing = json.loads(tokens_path.read_text()) if tokens_path.exists() else {}
    existing.update(report)
    tokens_path.write_text(json.dumps(existing, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
