#!/usr/bin/env python3
"""Generate cases/<kind>/<name>/case.inp and case.json from EPA's decks.

Reductions applied to every deck (see harness/cases.py for per-case options):
  * SO: keep only POINT sources (optionally only ``keep_sources``); drop every
    keyword that names a dropped source; optionally drop building keywords.
    Keep only the SRCGROUP of the case's group.
  * CO: ERRORFIL errors.out; drop EVENTFIL. AVERTIME is left as EPA wrote it:
    with POLLUTID SO2, "AVERTIME 1" alone switches AERMOD into the 1-hr SO2
    NAAQS processing, which rejects less than a year of met (error E480).
  * ME: SURFFILE/PROFFILE point at basenames (the runner stages the files).
  * OU: replaced by one 1-hr PLOT POSTFILE for the case's group. FILEFORM is
    kept: HRDOW uses FILEFORM EXP, and dropping it changes the POSTFILE's
    number format (and so 70% of printed values) without changing physics.
  * EV: dropped.
Run after ref/fetch.py. Output is deterministic and committed.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
from cases import CASES, EPA_DIR, POSTFILE_NAME, Case  # noqa: E402

PATHWAYS = {"CO", "SO", "RE", "ME", "OU", "EV"}
BUILDING_KEYWORDS = {"BUILDHGT", "BUILDWID", "BUILDLEN", "XBADJ", "YBADJ"}
# SO keywords whose second field is a source ID (or source-ID range).
SOURCE_KEYED = BUILDING_KEYWORDS | {
    "LOCATION", "SRCPARAM", "EMISFACT", "AREAVERT", "URBANSRC", "HOUREMIS",
    "RBARRIER", "RDEPRESS", "METHOD_2", "PARTDIAM", "MASSFRAC", "PARTDENS",
    "GASDEPOS", "EMISUNIT", "OLMGROUP", "PSDGROUP", "BLPGROUP", "INCLUDED",
    "PLATFORM", "BACKGRND", "BGSECTOR", "NO2RATIO",
}
SO_DROP_IF_NO_LINE_SOURCES = {"BLPINPUT"}


def split_line(line: str) -> tuple[str | None, list[str]]:
    tokens = line.split()
    if tokens and tokens[0].upper() in PATHWAYS:
        return tokens[0].upper(), tokens[1:]
    return None, tokens


def point_sources(lines: list[str]) -> dict[str, str]:
    """Source ID -> source type, from LOCATION records."""
    out = {}
    for line in lines:
        _, rest = split_line(line)
        if len(rest) >= 3 and rest[0].upper() == "LOCATION":
            out[rest[1].upper()] = rest[2].upper()
    return out


def reduce_deck(text: str, case: Case) -> tuple[str, dict]:
    lines = text.splitlines()
    types = point_sources(lines)
    keep = {
        sid for sid, typ in types.items()
        if typ == "POINT" and (case.keep_sources is None or sid in case.keep_sources)
    }
    dropped_sources = sorted(set(types) - keep)
    removed = {"sources": dropped_sources, "keywords": {}}

    def note(kw: str) -> None:
        removed["keywords"][kw] = removed["keywords"].get(kw, 0) + 1

    out: list[str] = []
    path = None
    last_kw = None
    met: list[str] = []
    includes: list[str] = []
    fileform: list[str] = []
    for line in lines:
        if line.lstrip().startswith("**") or not line.strip():
            if path != "OU":
                out.append(line.rstrip())
            continue
        pw, rest = split_line(line)
        if pw:
            path = pw
        kw = rest[0].upper() if rest else ""
        if kw in ("STARTING", "FINISHED"):
            last_kw = None
            if path == "EV":
                continue
            if path == "OU" and kw == "FINISHED":
                out += [
                    "OU STARTING",
                    "   RECTABLE  ALLAVE  FIRST",
                    *fileform,
                    f"   POSTFILE  1  {case.group}  PLOT  {POSTFILE_NAME}",
                    "OU FINISHED",
                ]
                continue
            if path == "OU":
                continue
            out.append(line.rstrip())
            continue
        if path == "OU" and kw == "FILEFORM":
            fileform.append("   " + " ".join(rest))
            continue
        if path in ("EV", "OU"):
            continue
        if not re.fullmatch(r"[A-Z0-9_]+", kw) or (path == "RE" and kw not in _RE_KEYWORDS):
            kw = last_kw or kw  # blank keyword field continues the previous keyword
        else:
            last_kw = kw

        if path == "CO":
            if kw == "ERRORFIL":
                out.append("   ERRORFIL  errors.out")
                continue
            if kw == "EVENTFIL":
                note(kw)
                continue
        elif path == "SO":
            if case.strip_buildings and kw in BUILDING_KEYWORDS:
                note(kw)
                continue
            if kw in SOURCE_KEYED and len(rest) >= 2 and rest[0].upper() == kw:
                if rest[1].upper() not in keep:
                    note(kw)
                    continue
            if kw in SO_DROP_IF_NO_LINE_SOURCES and not any(
                types[s] == "BUOYLINE" for s in keep
            ):
                note(kw)
                continue
            if kw == "SRCGROUP":
                if rest[1].upper() != case.group.upper():
                    note(kw)
                    continue
                members = [m for m in rest[2:] if m.upper() in keep]
                if rest[1].upper() != "ALL" and not members:
                    raise SystemExit(f"{case.name}: group {case.group} has no POINT members left")
                out.append(f"   SRCGROUP  {rest[1]}  {'  '.join(members)}".rstrip())
                continue
        elif path == "ME" and kw in ("SURFFILE", "PROFFILE"):
            name = Path(rest[1].replace("\\", "/")).name
            met.append(name)
            out.append(f"   {kw}  {'  '.join([name, *rest[2:]])}")
            continue
        elif path == "RE" and kw == "INCLUDED":
            includes.append(rest[1])
        out.append(line.rstrip())

    if len(met) != 2:
        raise SystemExit(f"{case.name}: expected SURFFILE and PROFFILE, found {met}")
    return "\n".join(out) + "\n", {"removed": removed, "met": met, "includes": includes,
                                   "sources": sorted(keep)}


_RE_KEYWORDS = {
    "GRIDCART", "GRIDPOLR", "DISCCART", "DISCPOLR", "EVALCART", "ELEVUNIT",
    "INCLUDED", "STARTING", "FINISHED",
}


def build(case: Case) -> Path:
    src = EPA_DIR / "inputs" / case.deck
    if not src.exists():
        raise SystemExit(f"missing {src}; run ref/fetch.py first")
    raw = src.read_bytes()
    text, info = reduce_deck(raw.decode("latin-1"), case)
    case.dir.mkdir(parents=True, exist_ok=True)
    case.inp.write_text(text)
    manifest = {
        "name": case.name,
        "tier": case.tier,
        "kind": case.kind,
        "group": case.group,
        "deck": f"inputs/{case.deck}",
        "deck_sha256": hashlib.sha256(raw).hexdigest(),
        "epa_postfile": f"postfiles/{case.epa_postfile}" if case.epa_postfile else None,
        "oracle": "our compiled binary (ref/aermod) run on case.inp",
        "met": [f"meteorology/{m}" for m in info["met"]],
        "includes": [f"inputs/{i}" for i in info["includes"]],
        "sources": info["sources"],
        "removed": info["removed"],
        "notes": case.notes,
    }
    (case.dir / "case.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return case.inp


def main() -> int:
    for case in CASES:
        path = build(case)
        print(f"{case.name:20s} tier {case.tier:7s} -> {path.relative_to(path.parents[3])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
