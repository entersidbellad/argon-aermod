"""Human-written glue between a case deck and the generated port.

AERMOD's SETUP phase and its output writers are not ported. This module does
their job for the scoped slice and hands the port arrays named after the MAIN1
module variables SETUP would have filled:

  * ``load_project(inp)`` -> ``Project``: the deck's sources (after PPARM's
    floors and PROFBASE's ZBASE reassignment), receptor networks expanded in
    AERMOD's order (INCLUDED files too), EMISFACT, STARTEND -> ISDATE/IEDATE.
    pyaermod parses the deck as a cross-check; options this module does not
    model are rejected.
  * ``load_met(project)`` -> ``Met``: the values METEXT's list-directed READ
    statements would assign, one array per READ-list variable.
  * ``setup_values(project, met)`` -> dict: every module variable the port reads
    but never assigns (harness/setup_inputs.json), as SETUP leaves it before
    HRLOOP. Numbers go through ``stodbl``, a port of AERMOD's runstream parser.
  * ``expected_dates`` and ``Result``: what the port's run_case must return.
  * ``write_postfile(...)``: a 1-hr PLOT POSTFILE in the FORMAT AERMOD uses.

Coordinates use the same double-precision expressions as the Fortran (reset.f
GENCAR/SETCAR/GENPOL/SETPOL/DISCAR/DISPOL/EVCART). tests/test_harness.py checks
receptors and the POSTFILE round trip against every oracle POSTFILE, and
setup_values against the SETUP.DMP that ref/aermod_dump writes.
"""

from __future__ import annotations

import json
import logging
import math
import re
import warnings
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
from pyaermod.input_generator import AERMODProject
from pyaermod.input_reader import read_aermod_input
from pyaermod.sources import PointSource

PI = 4.0 * math.atan(1.0)             # setup.f VARINI
DTORAD = PI / 180.0
IEDATE_NONE = 2147123124              # setup.f: no STARTEND
BUILDING_KEYS = {"BUILDHGT": "ADSBH", "BUILDWID": "ADSBW", "BUILDLEN": "ADSBL",
                 "XBADJ": "ADSXADJ", "YBADJ": "ADSYADJ"}
EMISFACT_SIZES = {"SEASON": 4, "MONTH": 12, "HROFDY": 24, "WSPEED": 6, "SEASHR": 96,
                  "HRDOW": 72, "HRDOW7": 168, "SHRDOW": 288, "SHRDOW7": 672,
                  "MHRDOW": 864, "MHRDOW7": 2016}
SURFACE_READ = ["IYEAR", "IMONTH", "IDAY", "IJDAY", "IHOUR", "SFCHF", "USTAR", "WSTAR",
                "VPTGZI", "ZICONV", "ZIMECH", "OBULEN", "SFCZ0", "BOWEN", "ALBEDO", "UREF",
                "WDREF", "UREFHT", "TA", "TREFHT", "IPCODE", "PRATE", "RH", "SFCP", "NCLOUD"]
SURFACE_INT = {"IYEAR", "IMONTH", "IDAY", "IJDAY", "IHOUR", "IPCODE", "NCLOUD"}
PROFILE_READ = ["KYEAR", "KMONTH", "KDAY", "KHOUR", "PFLHT", "JFLAG", "PFLWD", "PFLWS",
                "PFLTA", "PFLSA", "PFLSW"]
PROFILE_INT = {"KYEAR", "KMONTH", "KDAY", "KHOUR", "JFLAG"}
PATHWAYS = {"CO", "SO", "RE", "ME", "OU", "EV"}
RE_KEYWORDS = {"GRIDCART", "GRIDPOLR", "DISCCART", "DISCPOLR", "EVALCART", "ELEVUNIT",
               "INCLUDED", "STARTING", "FINISHED"}
GRID_SUBKEYS = {"STA", "END", "XYINC", "XPNTS", "YPNTS", "ORIG", "DIST", "DDIR", "GDIR",
                "ELEV", "HILL", "FLAG"}
# Keywords and MODELOPT options this module models and some case exercises (so
# setup_values is checked against AERMOD for them). Anything else is rejected so
# an unmodelled option never passes silently; add a case before widening these.
KNOWN_KEYWORDS = {
    "CO": {"STARTING", "FINISHED", "TITLEONE", "TITLETWO", "MODELOPT", "AVERTIME", "POLLUTID",
           "RUNORNOT", "ERRORFIL"},
    "SO": {"STARTING", "FINISHED", "ELEVUNIT", "LOCATION", "SRCPARAM", "BUILDHGT", "BUILDWID",
           "BUILDLEN", "XBADJ", "YBADJ", "EMISFACT", "SRCGROUP"},
    "ME": {"STARTING", "FINISHED", "SURFFILE", "PROFFILE", "SURFDATA", "UAIRDATA", "SITEDATA",
           "PROFBASE", "STARTEND"},
    "OU": {"STARTING", "FINISHED", "RECTABLE", "POSTFILE", "FILEFORM"},
}
MODELOPT_ALLOWED = {"CONC", "FLAT", "ELEV", "BETA", "ALPHA", "WARNCHKD"}
ME_IMSTAT = {"STARTING": 1, "SURFFILE": 2, "PROFFILE": 3, "SURFDATA": 4, "UAIRDATA": 5,
             "STARTEND": 6, "SITEDATA": 9, "PROFBASE": 10, "FINISHED": 50}   # meset.f MECARD
DAY_OF_WEEK_QFLAGS = {"HRDOW", "HRDOW7", "SHRDOW", "SHRDOW7", "MHRDOW", "MHRDOW7"}
# modules.f DATA GRIDHT, first 29 levels: soset.f locates stack tops in these (<= 600 m).
GRIDHT_29 = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 14.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0,
             90.0, 100.0, 120.0, 140.0, 160.0, 180.0, 200.0, 250.0, 300.0, 350.0, 400.0,
             450.0, 500.0, 550.0, 600.0)
# Module variables harness/setup_inputs.py flags but that the ported code only ever
# assigns through a CALL argument or names as an IOSTAT= specifier.
SETUP_SCRATCH = {"FNUM", "IMIT", "IOERRN", "IOSTAT"}


@dataclass(frozen=True)
class Source:
    """One POINT source, fields named after MAIN1 source arrays (deck order = ISRC)."""
    isrc: int                          # 1-based AERMOD source index
    SRCID: str
    AXS: float
    AYS: float
    AZS: float
    AQS: float                         # g/s
    AHS: float
    ATS: float
    AVS: float
    ADS: float
    flat: bool                         # LOCATION ... FLAT (L_FlatSrc)
    building: Optional[dict[str, np.ndarray]] = None   # ADSBH/ADSBW/ADSBL/ADSXADJ/ADSYADJ (36)
    QFLAG: Optional[str] = None        # EMISFACT type, e.g. "HRDOW"
    QFACT: Optional[np.ndarray] = None
    in_group: bool = True


@dataclass(frozen=True)
class Receptors:
    """Receptors in AERMOD's index order (IREC = position + 1)."""
    AXR: np.ndarray
    AYR: np.ndarray
    AZELEV: np.ndarray
    AZHILL: np.ndarray
    AZFLAG: np.ndarray
    NETID: tuple[str, ...]
    RECTYP: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.AXR)


@dataclass
class Project:
    inp: Path
    deck: AERMODProject                # pyaermod's parse, for anything not lifted out below
    MODELOPT: tuple[str, ...]          # CO MODELOPT keywords, upper case
    POLLUT: str
    FLAT: bool
    ELEV: bool
    FLGPOL: bool
    AZFLAG_DEFAULT: float
    ISDATE: int
    IEDATE: int
    ZBASE: float                       # ME PROFBASE
    sources: list[Source]              # every source in the deck, ISRC order
    group: str                         # POSTFILE source group
    receptors: Receptors
    file_format: str                   # "FIX" or "EXP" (OU FILEFORM)
    cards: dict[str, list[list[str]]] = field(default_factory=dict)   # pathway -> token lists
    title: str = ""

    @property
    def group_sources(self) -> list[Source]:
        return [s for s in self.sources if s.in_group]


@dataclass
class Met:
    sfc_path: Path
    pfl_path: Path
    surface: dict[str, np.ndarray]     # one entry per SURFACE_READ name, one row per record
    profile: dict[str, np.ndarray]     # one entry per PROFILE_READ name, one row per level
    profile_start: np.ndarray          # hour h uses profile rows profile_start[h]:profile_start[h+1]
    sfc_headers: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.surface["IYEAR"])


@dataclass
class Result:
    """What the port's run_case returns (prompts/contract.md)."""
    dates: np.ndarray                  # int64 KURDAT (YYMMDDHH), one per hour HRLOOP processed
    conc: np.ndarray                   # float64 [hour, receptor], ug/m^3, POSTFILE group total
    debug: list[tuple] = field(default_factory=list)
    # debug rows: (KURDAT, ISRC, IREC, comp, sub, var, value) in the order AERMOD would
    # print them; names and keys as in prompts/debug_vars.md (harness/dbgparse.py).


# --- deck tokenising ---------------------------------------------------------

def _cards(path: Path, pathway: str) -> list[list[str]]:
    """Token lists of every card in ``pathway`` (INCLUDED files expanded), pathway dropped."""
    out: list[list[str]] = []
    current = None
    for raw in path.read_text(errors="replace").splitlines():
        if raw.lstrip().startswith("**") or not raw.strip():
            continue
        toks = raw.split()
        if toks[0].upper() in PATHWAYS:
            current = toks[0].upper()
            toks = toks[1:]
        if current != pathway or not toks:
            continue
        if toks[0].upper() == "INCLUDED" and len(toks) > 1:
            inc = path.parent / toks[1]
            out += _cards_included(inc, pathway)
            continue
        out.append(toks)
    return out


def _cards_included(path: Path, pathway: str) -> list[list[str]]:
    out = []
    for raw in path.read_text(errors="replace").splitlines():
        if raw.lstrip().startswith("**") or not raw.strip():
            continue
        toks = raw.split()
        if toks[0].upper() in PATHWAYS:
            if toks[0].upper() != pathway:
                continue
            toks = toks[1:]
        if toks:
            out.append(toks)
    return out


def stodbl(text: str) -> tuple[float, int]:
    """AERMOD's STODBL: (value, repeat count) of one field, bit-for-bit.

    AERMOD reads every runstream number this way, digit by digit in double
    precision, which is not correctly rounded (``62.26`` -> 62.260000000000005),
    so ``float()`` would give the port different inputs from AERMOD's.
    """
    cnum, head, fdec, imuti = 0.0, 0.0, 1.0, 1
    nmark = pmark = dmark = mmark = emark = False
    started = False
    for chk in text.upper():
        if chk == " ":
            if started:
                break
            continue
        started = True
        if "0" <= chk <= "9":
            if not dmark:
                cnum = cnum * 10.0 + float(ord(chk) - 48)
            else:
                fdec = fdec / 10.0
                cnum = cnum + fdec * float(ord(chk) - 48)
        elif dmark and not emark and chk in "ED":
            emark = True
            head = -cnum if nmark else cnum
            dmark = nmark = False
            cnum = 0.0
        elif not pmark and chk == "+":
            pmark = True
        elif not nmark and chk == "-":
            nmark = True
        elif not dmark and chk == ".":
            dmark = True
        elif not mmark and chk == "*" and not nmark:
            mmark = True
            imuti = _nint(cnum)
            cnum = 0.0
        else:
            raise ValueError(f"invalid number {text!r}")
    fnum = -cnum if nmark else cnum
    if emark:
        fnum = head * 10.0 ** fnum if abs(fnum) <= 30.0 else (
            0.0 if fnum < 0.0 else head * 10.0 ** 30.0 if fnum > 0.0 else fnum)
    return fnum, imuti


def _nint(x: float) -> int:
    """Fortran NINT/IDNINT: round half away from zero."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def num(text: str) -> float:
    value, count = stodbl(text)
    if count != 1:
        raise ValueError(f"repeat count not allowed here: {text!r}")
    return value


def _numbers(tokens: list[str]) -> list[float]:
    """STODBL every field, expanding AERMOD 'n*value' repeats."""
    out: list[float] = []
    for t in tokens:
        value, count = stodbl(t)
        out += [value] * count
    return out


# --- receptors ---------------------------------------------------------------

@dataclass
class _Grid:
    kind: str
    netid: str
    xint: float = 0.0
    yint: float = 0.0
    xs: list[float] = field(default_factory=list)      # XCOORD (distances for polar)
    ys: list[float] = field(default_factory=list)      # YCOORD (directions for polar)
    rows: dict[str, dict[int, list[float]]] = field(default_factory=dict)


def _expand_grid(g: _Grid, src_xy: dict[str, tuple[float, float]], acc: dict) -> None:
    """SETCAR / SETPOL: J (y or direction) outer, I (x or distance) inner."""
    for j, yc in enumerate(g.ys, start=1):
        for i, xc in enumerate(g.xs, start=1):
            if g.kind == "GRIDPOLR":
                ytemp = yc * DTORAD
                acc["AXR"].append(g.xint + xc * math.sin(ytemp))
                acc["AYR"].append(g.yint + xc * math.cos(ytemp))
            else:
                acc["AXR"].append(xc)
                acc["AYR"].append(yc)
            for key, arr in (("ELEV", "AZELEV"), ("HILL", "AZHILL"), ("FLAG", "AZFLAG")):
                row = g.rows.get(key, {}).get(j)
                acc[arr].append(row[i - 1] if row else None)
            acc["NETID"].append(g.netid)
            acc["RECTYP"].append("GP" if g.kind == "GRIDPOLR" else "GC")


def expand_receptors(cards: list[list[str]], src_xy: dict[str, tuple[float, float]],
                     elev: bool, flgpol: bool, azflag_default: float) -> Receptors:
    acc: dict[str, list] = {k: [] for k in ("AXR", "AYR", "AZELEV", "AZHILL", "AZFLAG",
                                            "NETID", "RECTYP")}
    grid: Optional[_Grid] = None
    last_kw = None
    for toks in cards:
        kw = toks[0].upper()
        if kw in RE_KEYWORDS:
            last_kw, args = kw, toks[1:]
        else:
            kw, args = last_kw, toks
        if kw in (None, "STARTING", "FINISHED", "ELEVUNIT"):
            continue
        if kw in ("GRIDCART", "GRIDPOLR"):
            if args and args[0].upper() not in GRID_SUBKEYS:
                netid, args = args[0].upper(), args[1:]
            else:
                netid = grid.netid if grid else ""
            sub = args[0].upper()
            vals = args[1:]
            if sub == "STA":
                grid = _Grid(kw, netid)
            elif grid is None:
                raise ValueError(f"{kw} {sub} before STA")
            elif sub == "END":
                _expand_grid(grid, src_xy, acc)
                grid = None
            elif sub == "XYINC":
                x0, nx, dx, y0, ny, dy = (num(v) for v in vals[:6])
                grid.xs = [x0 + dx * float(i) for i in range(_nint(nx))]
                grid.ys = [y0 + dy * float(j) for j in range(_nint(ny))]
            elif sub == "XPNTS":
                grid.xs += _numbers(vals)
            elif sub == "YPNTS":
                grid.ys += _numbers(vals)
            elif sub == "ORIG":
                if re.fullmatch(r"[-+.\dEeDd]+", vals[0]):
                    grid.xint, grid.yint = num(vals[0]), num(vals[1])
                else:
                    grid.xint, grid.yint = src_xy[vals[0].upper()]
            elif sub == "DIST":
                grid.xs += _numbers(vals)
            elif sub == "DDIR":
                grid.ys += _numbers(vals)
            elif sub == "GDIR":
                n, dirini, dirinc = _nint(num(vals[0])), num(vals[1]), num(vals[2])
                for j in range(n):
                    d = dirini + dirinc * float(j)
                    if d > 360.0:
                        d -= 360.0
                    elif d <= 0.0:
                        d += 360.0
                    grid.ys.append(d)
            elif sub in ("ELEV", "HILL", "FLAG"):
                grid.rows.setdefault(sub, {}).setdefault(_nint(num(vals[0])), []).extend(
                    _numbers(vals[1:]))
            else:
                raise ValueError(f"unsupported {kw} subkey {sub}")
            continue
        if kw == "DISCCART":
            v = [num(t) for t in args]
            ze = zh = zf = None
            if elev and flgpol:
                ze = v[2] if len(v) >= 3 else None
                zh = v[3] if len(v) >= 4 else None
                zf = v[4] if len(v) == 5 else None
            elif elev:
                ze = v[2] if len(v) >= 3 else None
                zh = v[3] if len(v) >= 4 else None
            elif flgpol:
                zf = v[2] if len(v) == 3 else (v[4] if len(v) == 5 else None)
            _append(acc, v[0], v[1], ze, zh, zf, "", "DC")
            continue
        if kw == "DISCPOLR":
            xs, ys = src_xy[args[0].upper()]
            v = [num(t) for t in args[1:]]
            rng, direct = v[0], v[1]
            ze = zh = zf = None
            if elev:
                ze = v[2] if len(v) >= 3 else None
                zh = v[3] if len(v) >= 4 else None
                zf = v[4] if flgpol and len(v) == 5 else None
            elif flgpol:
                zf = v[2] if len(v) == 3 else (v[4] if len(v) == 5 else None)
            _append(acc, xs + rng * math.sin(direct * DTORAD), ys + rng * math.cos(direct * DTORAD),
                    ze, zh, zf, "", "DP")
            continue
        if kw == "EVALCART":
            v = [num(t) for t in args[:5]]
            _append(acc, v[0], v[1], v[2] if elev else None, v[3] if elev else None,
                    v[4] if flgpol else None, "", "DC")
            continue
        raise ValueError(f"unsupported RE keyword {kw}")

    def arr(name: str, default: float) -> np.ndarray:
        return np.array([default if v is None else v for v in acc[name]], dtype=np.float64)

    return Receptors(
        AXR=np.array(acc["AXR"], dtype=np.float64), AYR=np.array(acc["AYR"], dtype=np.float64),
        AZELEV=arr("AZELEV", 0.0), AZHILL=arr("AZHILL", 0.0), AZFLAG=arr("AZFLAG", azflag_default),
        NETID=tuple(acc["NETID"]), RECTYP=tuple(acc["RECTYP"]))


def _append(acc: dict, x, y, ze, zh, zf, netid: str, rectyp: str) -> None:
    for k, v in (("AXR", x), ("AYR", y), ("AZELEV", ze), ("AZHILL", zh), ("AZFLAG", zf),
                 ("NETID", netid), ("RECTYP", rectyp)):
        acc[k].append(v)


# --- sources -----------------------------------------------------------------

def _emisfact(cards: list[list[str]]) -> dict[str, tuple[str, list[float]]]:
    out: dict[str, tuple[str, list[float]]] = {}
    for toks in cards:
        if toks[0].upper() != "EMISFACT":
            continue
        sid, qflag = toks[1].upper(), toks[2].upper()
        if "-" in sid:
            raise ValueError(f"EMISFACT source range {sid} not supported")
        prev = out.get(sid, (qflag, []))
        if prev[0] != qflag:
            raise ValueError(f"{sid}: EMISFACT {qflag} after {prev[0]}")
        out[sid] = (qflag, prev[1] + _numbers(toks[3:]))
    for sid, (qflag, vals) in out.items():
        if len(vals) != EMISFACT_SIZES[qflag]:
            raise ValueError(f"{sid}: EMISFACT {qflag} has {len(vals)} values, "
                             f"expected {EMISFACT_SIZES[qflag]}")
    return out


def _group_members(cards: list[list[str]], group: str) -> Optional[set[str]]:
    if group.upper() == "ALL":
        return None
    members = {t.upper() for toks in cards
               if toks[0].upper() == "SRCGROUP" and toks[1].upper() == group.upper()
               for t in toks[2:]}
    return members


def _pparm(ats: float, avs: float, ads: float) -> tuple[float, float, float]:
    """soset.f PPARM's adjustments to a POINT source's exit parameters."""
    if ats == 0.0:
        ats = -1.0e-5
    elif 0.0 < ats < 200.0:
        raise ValueError(f"stack temperature {ats} K < 200 K (AERMOD error 320)")
    if avs < 1.0e-5:
        avs = 1.0e-5
    if ads < 0.0:
        raise ValueError("negative stack diameter (AERMOD error 209)")
    if ads < 1.0e-5:
        ads = 1.0e-5
    return ats, avs, ads


def _sources(so_cards: list[list[str]], group: str, flatsrcs: bool) -> list[Source]:
    """soset.f SOLOCA/SOPARM/PPARM/DSFILL/EFFILL for POINT sources, deck order = ISRC."""
    emis = _emisfact(so_cards)
    members = _group_members(so_cards, group)
    loc: dict[str, tuple[float, float, float, bool]] = {}
    parm: dict[str, list[float]] = {}
    bld: dict[str, dict[str, list[float]]] = {}
    for toks in so_cards:
        kw = toks[0].upper()
        if kw == "LOCATION":
            sid, styp = toks[1].upper(), toks[2].upper()
            if styp != "POINT":
                raise ValueError(f"{sid}: only POINT sources are in scope, got {styp}")
            flat = len(toks) == 6 and toks[5].upper() == "FLAT"
            if flat and not flatsrcs:
                raise ValueError(f"{sid}: LOCATION ... FLAT needs MODELOPT FLAT ELEV")
            z = num(toks[5]) if len(toks) == 6 and not flat else 0.0
            loc[sid] = (num(toks[3]), num(toks[4]), z, flat)
        elif kw == "SRCPARAM":
            parm[toks[1].upper()] = [num(t) for t in toks[2:7]]
        elif kw in BUILDING_KEYS:
            if "-" in toks[1]:
                raise ValueError(f"{kw} source range {toks[1]} not supported")
            bld.setdefault(toks[1].upper(), {}).setdefault(BUILDING_KEYS[kw], []).extend(
                _numbers(toks[2:]))
    out = []
    for i, (sid, (x, y, z, flat)) in enumerate(loc.items(), start=1):
        building = None
        if sid in bld:
            if set(bld[sid]) != set(BUILDING_KEYS.values()) or any(
                    len(v) != 36 for v in bld[sid].values()):
                raise ValueError(f"{sid}: needs all five building keywords with 36 sectors each")
            building = {k: np.array(v) for k, v in bld[sid].items()}
        aqs, ahs, ats, avs, ads = parm[sid]
        ats, avs, ads = _pparm(ats, avs, ads)
        qflag, qfact = emis.get(sid, (None, None))
        out.append(Source(
            isrc=i, SRCID=sid, AXS=x, AYS=y, AZS=z, AQS=aqs, AHS=ahs, ATS=ats, AVS=avs, ADS=ads,
            flat=flat, building=building, QFLAG=qflag,
            QFACT=None if qfact is None else np.asarray(qfact, dtype=np.float64),
            in_group=members is None or sid in members))
    return out


def _check_against_pyaermod(deck: AERMODProject, sources: list[Source]) -> None:
    """pyaermod parses the same deck independently; disagreement means a glue bug."""
    theirs = deck.sources.sources
    if [s.source_id.upper() for s in theirs] != [s.SRCID for s in sources]:
        raise AssertionError("glue and pyaermod disagree on the source list")
    for p, s in zip(theirs, sources):
        if not isinstance(p, PointSource):
            raise AssertionError(f"pyaermod does not see {s.SRCID} as a POINT source")
        pairs = [(p.x_coord, s.AXS), (p.y_coord, s.AYS), (p.emission_rate, s.AQS),
                 (p.stack_height, s.AHS)]
        if p.building_height is not None or s.building is not None:
            pairs += list(zip(p.building_height, s.building["ADSBH"]))
        for a, b in pairs:
            if not math.isclose(float(a), b, rel_tol=1e-12, abs_tol=1e-12):
                raise AssertionError(f"{s.SRCID}: pyaermod {a} vs glue {b}")


# --- control / dates ---------------------------------------------------------

def _cent(yy: int) -> int:
    """meset.f CENT_DATE for a 2-digit year."""
    if yy > 99:
        return yy
    return (1900 if yy >= 50 else 2000) + yy


def _startend(me_cards: list[list[str]]) -> tuple[int, int]:
    for toks in me_cards:
        if toks[0].upper() != "STARTEND":
            continue
        v = [int(t) for t in toks[1:]]
        if len(v) == 6:
            isyr, ismn, isdy, ieyr, iemn, iedy = v
            ishr, iehr = 1, 24
        elif len(v) == 8:
            isyr, ismn, isdy, ishr, ieyr, iemn, iedy, iehr = v
        else:
            raise ValueError(f"STARTEND with {len(v)} fields")
        isyr, ieyr = _cent(isyr), _cent(ieyr)
        return (isyr * 1000000 + ismn * 10000 + isdy * 100 + ishr,
                ieyr * 1000000 + iemn * 10000 + iedy * 100 + iehr)
    return 0, IEDATE_NONE


def _postfile_group(ou_cards: list[list[str]]) -> tuple[str, str]:
    group, fmt = None, "FIX"
    for toks in ou_cards:
        kw = toks[0].upper()
        if kw == "POSTFILE":
            if toks[1] != "1" or toks[3].upper() != "PLOT":
                raise ValueError("only a 1-hr PLOT POSTFILE is supported")
            group = toks[2].upper()
        elif kw == "FILEFORM":
            fmt = toks[1].upper()
    if group is None:
        raise ValueError("deck has no POSTFILE")
    return group, fmt


def load_project(inp: Path | str) -> Project:
    inp = Path(inp)
    reader_log = logging.getLogger("pyaermod.input_reader")
    level = reader_log.level
    reader_log.setLevel(logging.ERROR)      # it warns about every keyword this module parses itself
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            deck = read_aermod_input(inp)
    finally:
        reader_log.setLevel(level)
    co, so, re_, me, ou = (_cards(inp, p) for p in ("CO", "SO", "RE", "ME", "OU"))
    modelopt = tuple(t.upper() for toks in co if toks[0].upper() == "MODELOPT" for t in toks[1:])
    for pathway, cards in (("CO", co), ("SO", so), ("ME", me), ("OU", ou)):
        unknown = {t[0].upper() for t in cards} - KNOWN_KEYWORDS[pathway]
        if unknown:
            raise ValueError(f"out of scope {pathway} keywords: {sorted(unknown)}")
    if set(modelopt) - MODELOPT_ALLOWED:
        raise ValueError(f"out of scope MODELOPT: {sorted(set(modelopt) - MODELOPT_ALLOWED)}")
    for toks in so + re_:
        if toks[0].upper() == "ELEVUNIT" and toks[1].upper() != "METERS":
            raise ValueError(f"ELEVUNIT {toks[1]} not supported (METERS only)")
    if "FLAT" not in modelopt:
        raise ValueError("MODELOPT FLAT is required (flat terrain is the port's scope)")
    elev = "ELEV" in modelopt                  # coset.f: FLAT plus ELEV sets FLATSRCS
    flgpol, azflag_default = False, 0.0        # FLAGPOLE is rejected above
    group, fmt = _postfile_group(ou)
    sources = _sources(so, group, flatsrcs=elev)
    _check_against_pyaermod(deck, sources)
    src_xy = {s.SRCID: (s.AXS, s.AYS) for s in sources}
    isdate, iedate = _startend(me)
    zbase = next((num(t[1]) for t in me if t[0].upper() == "PROFBASE"), 0.0)
    # meset.f PROFBASE: under FLAT, sources (only FLAT ones when FLATSRCS) sit at ZBASE.
    sources = [replace(s, AZS=zbase) if (s.flat or not elev) else s for s in sources]
    receptors = expand_receptors(re_, src_xy, elev, flgpol, azflag_default)
    if not elev:
        n = len(receptors)
        receptors = replace(receptors, AZELEV=np.full(n, zbase), AZHILL=np.full(n, zbase))
    return Project(
        inp=inp, deck=deck, MODELOPT=modelopt,
        POLLUT=next((t[1].upper() for t in co if t[0].upper() == "POLLUTID"), ""),
        FLAT="FLAT" in modelopt, ELEV=elev, FLGPOL=flgpol, AZFLAG_DEFAULT=azflag_default,
        ISDATE=isdate, IEDATE=iedate, ZBASE=zbase, sources=sources, group=group,
        receptors=receptors,
        file_format=fmt, cards={"CO": co, "SO": so, "RE": re_, "ME": me, "OU": ou},
        title=deck.control.title_one or "")


# --- meteorology -------------------------------------------------------------

def _read_free(path: Path, names: list[str], ints: set[str],
               headers: Optional[list[str]] = None) -> dict[str, np.ndarray]:
    cols: dict[str, list] = {n: [] for n in names}
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        if ":" in line:
            if headers is not None:
                headers.append(line.rstrip())
            continue
        toks = line.split()
        if len(toks) < len(names):
            raise ValueError(f"{path.name}: short record {line!r}")
        for n, t in zip(names, toks):
            cols[n].append(int(t) if n in ints else float(t))
    return {n: np.array(v, dtype=np.int64 if n in ints else np.float64) for n, v in cols.items()}


def load_met(project: Project, met_dir: Path | str | None = None) -> Met:
    """Read the deck's SURFFILE/PROFFILE (looked up in ``met_dir``, default the deck's dir)."""
    base = Path(met_dir) if met_dir else project.inp.parent
    sfc = base / Path(project.deck.meteorology.surface_file).name
    pfl = base / Path(project.deck.meteorology.profile_file).name
    headers: list[str] = []
    surface = _read_free(sfc, SURFACE_READ, SURFACE_INT, headers)
    profile = _read_free(pfl, PROFILE_READ, PROFILE_INT)
    return Met(sfc_path=sfc, pfl_path=pfl, surface=surface, profile=profile,
               profile_start=_profile_start(surface, profile), sfc_headers=headers)


def expected_dates(project: Project, met: Met) -> np.ndarray:
    """KURDAT of every surface record inside STARTEND (what HRLOOP writes to the POSTFILE)."""
    s = met.surface
    year = np.where(s["IYEAR"] < 100, [_cent(int(y)) for y in s["IYEAR"]], s["IYEAR"])
    mdh = s["IMONTH"] * 10000 + s["IDAY"] * 100 + s["IHOUR"]
    full = year * 1000000 + mdh
    keep = (full >= project.ISDATE) & (full <= project.IEDATE)
    return ((year % 100) * 1000000 + mdh)[keep].astype(np.int64)


def _profile_start(surface: dict[str, np.ndarray], profile: dict[str, np.ndarray]) -> np.ndarray:
    """Row offsets of each hour's profile levels; the profile file must track the surface file."""
    pkey = np.stack([profile[k] for k in ("KYEAR", "KMONTH", "KDAY", "KHOUR")], axis=1)
    skey = np.stack([surface[k] for k in ("IYEAR", "IMONTH", "IDAY", "IHOUR")], axis=1)
    starts = np.flatnonzero(np.r_[True, np.any(pkey[1:] != pkey[:-1], axis=1)])
    if len(starts) != len(skey) or not np.array_equal(pkey[starts], skey):
        raise ValueError(f"profile file has {len(starts)} hours that do not line up with "
                         f"the {len(skey)} surface records")
    return np.r_[starts, len(pkey)].astype(np.int64)


# --- MAIN1 values SETUP assigns ----------------------------------------------

def _locate(parray: tuple[float, ...], value: float) -> int:
    """LOCATE(PARRAY, 1, len, VALUE, NDXBLW): 1-based index of the level at or below VALUE."""
    jl, ju = 0, len(parray) + 1
    while ju - jl > 1:
        jm = (ju + jl) // 2
        if value >= parray[jm - 1]:
            jl = jm
        else:
            ju = jm
    return jl


def _julian(year: int, month: int, day: int) -> int:
    return (date(year, month, day) - date(year, 1, 1)).days + 1


def _station(me: list[list[str]], keyword: str) -> tuple[int, int, str]:
    """meset.f SURFID/UAIRID: station id, year, name ('UNKNOWN' when omitted)."""
    toks = next(t for t in me if t[0].upper() == keyword)
    return (_nint(float(toks[1])), _nint(float(toks[2])),
            toks[3].upper() if len(toks) > 3 else "UNKNOWN")


def _met_file(me: list[list[str]], keyword: str) -> str:
    toks = next(t for t in me if t[0].upper() == keyword)
    if len(toks) > 2 and toks[2].upper() != "FREE":
        raise ValueError(f"{keyword} format {toks[2]!r} not supported (FREE only)")
    return toks[1]


def setup_values(project: Project, met: Met) -> dict[str, object]:
    """Every module variable the ported code reads that only SETUP assigns.

    Keys are the Fortran names listed in harness/setup_inputs.json (minus
    SETUP_SCRATCH); values have the Fortran shape (column-major indexing, so
    ADSBH[k-1, isrc-1] is ADSBH(K,ISRC)); None means AERMOD leaves the array
    unallocated, so the ported code must not touch it. tests/test_glue.py checks
    every value against a SETUP.DMP written by ref/aermod_dump.
    """
    srcs, rec = project.sources, project.receptors
    nsrc, co, me = len(srcs), project.cards["CO"], project.cards["ME"]
    zeros = np.zeros(nsrc)
    ave = next(t[1:] for t in co if t[0].upper() == "AVERTIME")
    kave = [int(t) for t in ave if t.isdigit()]
    nqf = max((EMISFACT_SIZES[s.QFLAG] for s in srcs if s.QFLAG), default=0)
    qfact = None
    if nqf:
        qfact = np.zeros((nqf, nsrc))
        for s in srcs:
            if s.QFACT is not None:
                qfact[:len(s.QFACT), s.isrc - 1] = s.QFACT
    nsec = 36 if any(s.building is not None for s in srcs) else 0
    bld = {}
    for key in ("ADSBH", "ADSBW", "ADSBL", "ADSXADJ", "ADSYADJ"):
        bld[key] = None
        if nsec:
            bld[key] = np.zeros((nsec, nsrc))
            for s in srcs:
                if s.building is not None:
                    bld[key][:, s.isrc - 1] = s.building[key]
    imstat = np.zeros(50, dtype=np.int64)
    for t in me:
        imstat[ME_IMSTAT[t[0].upper()] - 1] += 1
    idsurf, _, sfname = _station(me, "SURFDATA")
    iduair, iuyear, uaname = _station(me, "UAIRDATA")
    header = met.sfc_headers[0] if met.sfc_headers else ""
    isjday = 0
    if project.ISDATE:
        y, rest = divmod(project.ISDATE, 1000000)
        isjday = _julian(y, rest // 10000, rest // 100 % 100)
    modelopt = set(project.MODELOPT)

    values: dict[str, object] = {
        # sources (soset.f PPARM / SOCARD, deck order)
        "NSRC": nsrc, "NUMSRC": nsrc,
        "SRCID": np.array([s.SRCID for s in srcs], dtype=object),
        "SRCTYP": np.array(["POINT"] * nsrc, dtype=object),
        "AXS": np.array([s.AXS for s in srcs]), "AYS": np.array([s.AYS for s in srcs]),
        "AZS": np.array([s.AZS for s in srcs]), "AQS": np.array([s.AQS for s in srcs]),
        "AHS": np.array([s.AHS for s in srcs]), "ATS": np.array([s.ATS for s in srcs]),
        "AVS": np.array([s.AVS for s in srcs]), "ADS": np.array([s.ADS for s in srcs]),
        "ADSFACT": np.ones(nsrc),
        "L_FLATSRC": np.array([s.flat for s in srcs]),
        "NDXSTK": np.array([_locate(GRIDHT_29, s.AHS) for s in srcs], dtype=np.int64),
        "QFLAG": np.array([s.QFLAG or "" for s in srcs], dtype=object), "QFACT": qfact,
        "L_DAYOFWEEKOPTS": any(s.QFLAG in DAY_OF_WEEK_QFLAGS for s in srcs),
        "NSEC": nsec, **bld,
        "IGROUP": np.array([[1 if s.in_group else 0] for s in srcs], dtype=np.int64),
        "NUMGRP": 1,
        "AFTSRC": np.array(["N"] * nsrc, dtype=object),
        "URBSRC": np.array(["N"] * nsrc, dtype=object),
        "EVAL": np.zeros(nsrc, dtype=bool), "L_HRLYSIG": np.zeros(nsrc, dtype=bool),
        "OSPLAT": np.zeros(nsrc, dtype=bool),
        "INPD": np.zeros(nsrc, dtype=np.int64), "HOUREMISARRAY": np.zeros(nsrc, dtype=np.int64),
        **{k: zeros.copy() for k in ("AAFR", "ABA", "ABH", "ABL", "ABW", "ABYPR", "AFP",
                                     "AMFUEL", "ARPWR", "ASRCANGLE", "ASYINI", "ASZINI",
                                     "ATHRUST", "AVAA", "HENRY", "PLATHB", "PLATWB")},
        # receptors (reset.f)
        "NUMREC": len(rec), "AXR": rec.AXR, "AYR": rec.AYR, "AZELEV": rec.AZELEV,
        "AZHILL": rec.AZHILL, "AZFLAG": rec.AZFLAG,
        # control (coset.f)
        "POLLUT": project.POLLUT, "ELEV": project.ELEV, "L_WARNCHKD": "WARNCHKD" in modelopt,
        "NUMAVE": len(kave), "KAVE": np.array(kave, dtype=np.int64),
        "PERIOD": any(t.upper() == "PERIOD" for t in ave),
        "ANNUAL": any(t.upper() == "ANNUAL" for t in ave),
        **{k: np.zeros(len(kave), dtype=np.int64) for k in ("IDYTAB", "ITOXFL", "ITXUNT")},
        # meteorology (meset.f, and the surface file header meset.f reads)
        "METINP": _met_file(me, "SURFFILE"), "PROINP": _met_file(me, "PROFFILE"),
        "METFRM": "FREE", "PROFRM": "FREE",
        "IDSURF": idsurf, "IDUAIR": iduair, "IUYEAR": iuyear, "SFNAME": sfname,
        "UANAME": uaname, "ZBASE": project.ZBASE, "IEDATE": project.IEDATE,
        "ISJDAY": isjday, "IMSTAT": imstat,
        "L_ADJUSTAR": "ADJ_U*" in header, "L_BULKRN": "BULKRN" in header,
        # setup.f VARINI constants
        "PI": PI, "TWOPI": 2.0 * PI, "RTOFPI": math.sqrt(PI), "SRT2PI": math.sqrt(2.0 * PI),
        "RTOF2": math.sqrt(2.0), "RTPIBY2": math.sqrt(PI / 2.0), "RT2BYPI": math.sqrt(2.0 / PI),
        "DTORAD": DTORAD,
    }
    values.update(SCOPE_FIXED)
    missing = set(SETUP_INPUT_NAMES) - SETUP_SCRATCH - set(values)
    if missing:
        raise AssertionError(f"setup_values does not provide {sorted(missing)}")
    return values


# Values SETUP assigns that are the same for every deck load_project accepts: the
# defaults of options outside the scope, unit numbers, and fixed tuning constants.
# None = left unallocated (array for an out-of-scope source type or option).
SCOPE_FIXED: dict[str, object] = {
    **{k: None for k in ("AALPHA", "AANGLE", "APDEFF", "APDENS", "APDIAM", "APHI", "ATSTOP",
                         "AVGRAV", "AXCNTR", "AXINIT", "AXVERT", "AYCNTR", "AYINIT", "AYVERT",
                         "IURBGRP", "NVERTS", "URBPOP", "URBZ0", "VDEP", "WASHOUT")},
    **{k: False for k in (
        "ARM2", "AWMADWDBG", "DAYTAB", "DDEP", "DEBUG", "DEPOS", "DFAULT", "EVONLY",
        "FASTAREA", "GRSM", "HOURLY", "LDGAS", "LDPART", "LUSERVD", "LWGAS", "LWPART",
        "L_AWMA_ENTRAIN", "L_AWMA_UEFF", "L_AWMA_UTURB", "L_AWMA_UTURBHX", "L_BACKGRND",
        "L_BGHOURLY", "L_BGSECTOR", "L_BLSOURCE", "L_EFFSIGY", "L_MAXDCONT", "L_NOXHOURLY",
        "L_NOXSECTOR", "L_O3HOURLY", "L_O3SECTOR", "L_ORD_CAV", "L_ORD_TURB", "L_ORD_UEFF",
        "L_PBAL", "L_RECT_BLDG", "L_SKIPMESSAGES", "L_STRMLN_BLDG", "L_USERFRANMAX",
        "L_USERFRANMIN", "L_VECTORWS", "METEORDBG", "MONTH", "MULTYR", "MXFILE", "NO2AVE",
        "NOBID", "NOCHKD", "NOSTD", "O3MISS", "OLM", "PLATFMDBG", "PM25AVE", "PRIMEDBG",
        "PSDCREDIT", "PVMRM", "RSTINP", "RSTSAV", "RUNTTRM", "RUNTTRM2", "SCIM", "SCIMOUT",
        "SCREEN", "SEASONHR", "SO2AVE", "SUMMFILE", "TXFILE", "URBAN", "URBDBUG", "WDEP")},
    **{k: True for k in ("CLMPRO", "CONC", "L_URBANTRANSITION", "MSGPRO", "PPFILE")},
    **{k: np.zeros(6, dtype=bool) for k in ("L_BGVALUES", "L_NOXVALUE", "L_NOX_VALS",
                                            "L_O3VAL", "L_O3VALUES")},
    "TURBOPTS": np.zeros(9, dtype=bool),
    "BGSECT": np.zeros(6), "NOXSECT": np.zeros(6), "O3SECT": np.zeros(6),
    "NOXBACK": np.full(6, -999.0), "O3BACK": np.full(6, -999.0),
    "RL_GRIDWS": np.zeros((87, 3)), "EMIFAC": np.array([1.0e6]),    # CONC, g/s -> ug/m^3
    "IPROCL": np.ones(366, dtype=np.int64), "ISEAHR": np.zeros(1, dtype=np.int64),
    **{k: 0 for k in ("FULLHRQ", "IEVENT", "IPAIR", "IYR", "I_ALPHA", "NDX4ZI", "NREGINT",
                      "NREGSTART", "NUMBLGRPS", "NUMURB", "NUMYRS", "NURB")},
    **{k: 1 for k in ("INCRST", "NUMBGSECTS", "NUMNOXSECTS", "NUMO3SECTS", "NUMTYP")},
    "NYEARS": 5,
    "AWMADWDBUNT": 34, "DBGUNT": 24, "DBMUNT": 25, "IOUNIT": 8, "ISUMUNT": 28, "MFUNIT": 19,
    "MPUNIT": 21, "PLATFMDBUNT": 36, "PRMDBUNT": 27, "URBUNT": 37, "URBUNT1": 38,
    "URBUNT2": 40,
    **{k: 0.0 for k in ("DENOM", "EPSEFF", "EPSEFF3", "EPSEFFD", "FRACSAT", "FRANMIN",
                        "PLUME_SPREAD", "ROTANG", "SVAVG", "SWAVG", "UAVG", "USERVD", "ZRDEP")},
    "BIGT": 24.0, "EXPLIM": -50.0, "FRANMAX": 1.0, "MAXDIST": 1.0e20, "SVMIN": 0.2,
    "SWMIN": 0.02, "SZCOEF": 2.15, "WSMIN": 0.2828,
}
SETUP_INPUT_NAMES = tuple(v["name"] for v in json.loads(
    (Path(__file__).resolve().parent / "setup_inputs.json").read_text()))


# --- output ------------------------------------------------------------------

POSTFILE_COLUMNS = ("*        X             Y      AVERAGE CONC    ZELEV    ZHILL    ZFLAG"
                    "    AVE     GRP       DATE     NET ID")
POSTFILE_RULE = ("* ____________  ____________  ____________   ______   ______   ______  ______"
                 "  ________  ________  ________")


def _e13_6(v: float) -> str:
    """Fortran E13.6 (0.dddddd E+xx), as gfortran prints it."""
    if v == 0.0:
        return f"{'0.000000E+00':>13s}"
    m, e = f"{v:.5E}".split("E")
    digits = m.replace("-", "").replace(".", "")
    exp = int(e) + 1
    mant = f"0.{digits}"
    if len(mant) < 8:
        mant += "0" * (8 - len(mant))
    s = f"{'-' if v < 0 else ''}{mant}E{'+' if exp >= 0 else '-'}{abs(exp):02d}"
    return f"{s:>13s}"


def format_row(x: float, y: float, conc: float, ze: float, zh: float, zf: float,
               group: str, date: int, netid: str, file_format: str) -> str:
    """One record in AERMOD's PSTFRM (setup.f / coset.f)."""
    c = _e13_6(conc) if file_format == "EXP" else f"{conc:13.5f}"
    return (f" {x:13.5f} {y:13.5f} {c} {ze:8.2f} {zh:8.2f} {zf:8.2f}  {'1-HR':>6s}"
            f"  {group:<8s}  {date:08d}  {netid:<8s}")


def write_postfile(path: Path | str, project: Project, dates: np.ndarray, conc: np.ndarray) -> None:
    """conc[hour, receptor] in ug/m^3 for the POSTFILE group; dates are YYMMDDHH ints."""
    r = project.receptors
    if conc.shape != (len(dates), len(r)):
        raise ValueError(f"conc shape {conc.shape} != ({len(dates)}, {len(r)})")
    fmt = ("(2(1X,F13.5),1(1X,E13.6),3(1X,F8.2),2X,A6,2X,A8,2X,I8.8,2X,A8)"
           if project.file_format == "EXP" else
           "(3(1X,F13.5),3(1X,F8.2),2X,A6,2X,A8,2X,I8.8,2X,A8)")
    lines = [
        f"* AERMOD (26135 ): {project.title}",
        "* AERMET ( 26135):",
        f"* MODELING OPTIONS USED:   {'  '.join(project.MODELOPT)}",
        f"*         POST/PLOT FILE OF CONCURRENT  1-HR VALUES FOR SOURCE GROUP: {project.group:<8s}",
        f"*         FOR A TOTAL OF {len(r):5d} RECEPTORS.",
        f"*         FORMAT: {fmt}",
        POSTFILE_COLUMNS,
        POSTFILE_RULE,
    ]
    for h, kurdat in enumerate(dates):
        for i in range(len(r)):
            lines.append(format_row(r.AXR[i], r.AYR[i], float(conc[h, i]), r.AZELEV[i],
                                    r.AZHILL[i], r.AZFLAG[i], project.group, int(kurdat),
                                    r.NETID[i], project.file_format))
    Path(path).write_text("\n".join(lines) + "\n")
