"""Human-written glue between a case deck and the generated port.

AERMOD's SETUP phase and its output writers are not ported. This module does
their job for the scoped slice and hands the port arrays named after the MAIN1
module variables SETUP would have filled:

  * ``load_project(inp)`` -> ``Project``: pyaermod parses the deck; this module
    adds what pyaermod does not model (receptor networks expanded in AERMOD's
    order, INCLUDED receptor files, EMISFACT, STARTEND -> ISDATE/IEDATE).
  * ``load_met(project)`` -> ``Met``: the values METEXT's list-directed READ
    statements would assign, one array per READ-list variable.
  * ``write_postfile(...)``: a 1-hr PLOT POSTFILE in the FORMAT AERMOD uses.

Every coordinate is computed with the same double-precision expression as the
Fortran (reset.f GENCAR/SETCAR/GENPOL/SETPOL/DISCAR/DISPOL/EVCART), and
tests/test_glue.py checks the result against every oracle POSTFILE.
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field
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
# Keywords this module models (or that cannot change 1-hr concentrations). Anything
# else is rejected so an unmodelled option never passes silently.
KNOWN_KEYWORDS = {
    "CO": {"STARTING", "FINISHED", "TITLEONE", "TITLETWO", "MODELOPT", "AVERTIME", "POLLUTID",
           "RUNORNOT", "ERRORFIL", "FLAGPOLE"},
    "SO": {"STARTING", "FINISHED", "ELEVUNIT", "LOCATION", "SRCPARAM", "BUILDHGT", "BUILDWID",
           "BUILDLEN", "XBADJ", "YBADJ", "EMISFACT", "SRCGROUP"},
    "ME": {"STARTING", "FINISHED", "SURFFILE", "PROFFILE", "SURFDATA", "UAIRDATA", "SITEDATA",
           "PROFBASE", "STARTEND"},
    "OU": {"STARTING", "FINISHED", "RECTABLE", "POSTFILE", "FILEFORM"},
}
MODELOPT_ALLOWED = {"CONC", "FLAT", "ELEV", "DFAULT", "BETA", "ALPHA", "WARNCHKD", "NOWARN",
                    "NOCHKD"}


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


def _numbers(tokens: list[str]) -> list[float]:
    """Expand AERMOD 'n*value' repeats."""
    out: list[float] = []
    for t in tokens:
        if "*" in t:
            n, v = t.split("*", 1)
            out += [float(v)] * int(n)
        else:
            out.append(float(t))
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
                x0, nx, dx, y0, ny, dy = (float(v) for v in vals[:6])
                grid.xs = [x0 + dx * float(i) for i in range(int(nx))]
                grid.ys = [y0 + dy * float(j) for j in range(int(ny))]
            elif sub == "XPNTS":
                grid.xs += _numbers(vals)
            elif sub == "YPNTS":
                grid.ys += _numbers(vals)
            elif sub == "ORIG":
                if re.fullmatch(r"[-+.\dEeDd]+", vals[0]):
                    grid.xint, grid.yint = float(vals[0]), float(vals[1])
                else:
                    grid.xint, grid.yint = src_xy[vals[0].upper()]
            elif sub == "DIST":
                grid.xs += _numbers(vals)
            elif sub == "DDIR":
                grid.ys += _numbers(vals)
            elif sub == "GDIR":
                n, dirini, dirinc = int(float(vals[0])), float(vals[1]), float(vals[2])
                for j in range(n):
                    d = dirini + dirinc * float(j)
                    if d > 360.0:
                        d -= 360.0
                    elif d <= 0.0:
                        d += 360.0
                    grid.ys.append(d)
            elif sub in ("ELEV", "HILL", "FLAG"):
                grid.rows.setdefault(sub, {}).setdefault(int(float(vals[0])), []).extend(
                    _numbers(vals[1:]))
            else:
                raise ValueError(f"unsupported {kw} subkey {sub}")
            continue
        if kw == "DISCCART":
            v = [float(t) for t in args]
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
            v = [float(t) for t in args[1:]]
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
            v = [float(t) for t in args[:5]]
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


def _sources(deck: AERMODProject, so_cards: list[list[str]], group: str) -> list[Source]:
    emis = _emisfact(so_cards)
    members = _group_members(so_cards, group)
    flat_ids = {t[1].upper() for t in so_cards
                if t[0].upper() == "LOCATION" and t[-1].upper() == "FLAT"}
    out = []
    for i, s in enumerate(deck.sources.sources, start=1):
        if not isinstance(s, PointSource):
            raise ValueError(f"{s.source_id}: only POINT sources are in scope")
        bld = None
        if s.building_height is not None:
            bld = {
                "ADSBH": np.asarray(s.building_height, dtype=np.float64),
                "ADSBW": np.asarray(s.building_width, dtype=np.float64),
                "ADSBL": np.asarray(s.building_length, dtype=np.float64),
                "ADSXADJ": np.asarray(s.building_x_offset, dtype=np.float64),
                "ADSYADJ": np.asarray(s.building_y_offset, dtype=np.float64),
            }
            if any(len(v) != 36 for v in bld.values()):
                raise ValueError(f"{s.source_id}: building arrays must have 36 sectors")
        sid = s.source_id.upper()
        qflag, qfact = emis.get(sid, (None, None))
        out.append(Source(
            isrc=i, SRCID=sid, AXS=float(s.x_coord), AYS=float(s.y_coord),
            AZS=float(s.base_elevation), AQS=float(s.emission_rate), AHS=float(s.stack_height),
            ATS=float(s.stack_temp), AVS=float(s.exit_velocity), ADS=float(s.stack_diameter),
            flat=sid in flat_ids, building=bld, QFLAG=qflag,
            QFACT=None if qfact is None else np.asarray(qfact, dtype=np.float64),
            in_group=members is None or sid in members))
    return out


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
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        deck = read_aermod_input(inp)
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
    flagpole = [toks for toks in co if toks[0].upper() == "FLAGPOLE"]
    flgpol = bool(flagpole)
    azflag_default = float(flagpole[0][1]) if flagpole and len(flagpole[0]) > 1 else 0.0
    elev = "ELEV" in modelopt
    group, fmt = _postfile_group(ou)
    sources = _sources(deck, so, group)
    src_xy = {s.SRCID: (s.AXS, s.AYS) for s in sources}
    isdate, iedate = _startend(me)
    zbase = next((float(t[1]) for t in me if t[0].upper() == "PROFBASE"), 0.0)
    return Project(
        inp=inp, deck=deck, MODELOPT=modelopt,
        POLLUT=next((t[1].upper() for t in co if t[0].upper() == "POLLUTID"), ""),
        FLAT="FLAT" in modelopt, ELEV=elev, FLGPOL=flgpol, AZFLAG_DEFAULT=azflag_default,
        ISDATE=isdate, IEDATE=iedate, ZBASE=zbase, sources=sources, group=group,
        receptors=expand_receptors(re_, src_xy, elev, flgpol, azflag_default),
        file_format=fmt, title=deck.control.title_one or "")


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


def _profile_start(surface: dict[str, np.ndarray], profile: dict[str, np.ndarray]) -> np.ndarray:
    """Row offsets of each hour's profile levels; the profile file must track the surface file."""
    pkey = np.stack([profile[k] for k in ("KYEAR", "KMONTH", "KDAY", "KHOUR")], axis=1)
    skey = np.stack([surface[k] for k in ("IYEAR", "IMONTH", "IDAY", "IHOUR")], axis=1)
    starts = np.flatnonzero(np.r_[True, np.any(pkey[1:] != pkey[:-1], axis=1)])
    if len(starts) != len(skey) or not np.array_equal(pkey[starts], skey):
        raise ValueError(f"profile file has {len(starts)} hours that do not line up with "
                         f"the {len(skey)} surface records")
    return np.r_[starts, len(pkey)].astype(np.int64)


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
    for h, date in enumerate(dates):
        for i in range(len(r)):
            lines.append(format_row(r.AXR[i], r.AYR[i], float(conc[h, i]), r.AZELEV[i],
                                    r.AZHILL[i], r.AZFLAG[i], project.group, int(date),
                                    r.NETID[i], project.file_format))
    Path(path).write_text("\n".join(lines) + "\n")
