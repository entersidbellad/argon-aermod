"""Parse AERMOD DEBUGOPT files into ordered, keyed records.

Every record is named after the Fortran variable in the WRITE statement that
printed it, and tagged with that statement's subroutine, so a divergence can be
mapped straight to Fortran source. The labels and WRITE lists were read from
AERMOD 26135 (calc1.f DEBOUT/PCALC/PSRDEB/AER_PCHI/PRMCALC, calc2.f MEANDR,
iblval.f IBLVAL, prise.f DELTAH, metext.f METDEB, prime.f) and checked against
real AERTEST output by tests/test_dbgparse.py.

Key of a record: (date, isrc, irec, comp, sub, var, k)
  date  YYMMDDHH as int
  isrc  1-based source index in deck order (0 for met records)
  irec  1-based receptor index (0 for hour-level records; grid level for METDEB GRID*)
  comp  "" | "PAN" (meander/pancake pass) | "PLM" (coherent plume pass) | "PRIME"
  sub   Fortran subroutine that printed the value
  var   Fortran variable name from the WRITE list
  k     0-based occurrence of this (date, isrc, irec, comp, sub, var)
``tol`` is one unit in the last printed digit; values printed with full
list-directed precision get a 1e-9 relative floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?"


@dataclass(frozen=True)
class Record:
    date: int
    isrc: int
    irec: int
    comp: str
    sub: str
    var: str
    k: int
    value: float
    tol: float

    @property
    def key(self) -> tuple:
        return (self.date, self.isrc, self.irec, self.comp, self.sub, self.var, self.k)


def printed_tol(text: str) -> float:
    """One unit in the last printed digit of a Fortran-formatted number."""
    t = text.strip().upper().replace("D", "E")
    mant, _, exp = t.partition("E")
    decimals = len(mant.split(".")[1]) if "." in mant else 0
    unit = 10.0 ** (-decimals) * (10.0 ** int(exp) if exp else 1.0)
    return max(unit, abs(float(t)) * 1e-9) if decimals < 15 else abs(float(t)) * 1e-9


def _val(text: str) -> tuple[float, float]:
    t = text.strip()
    return float(t.upper().replace("D", "E")), printed_tol(t)


_FMT_ITEM = re.compile(r"(\d*)([AIFEX])(\d*)(?:\.(\d+))?")


def fixed_fields(line: str, fmt: str, names: list[str | None]) -> list[tuple[str, float, float]]:
    """Read a line with a Fortran edit-descriptor list; blank fields are skipped."""
    widths: list[tuple[str, int]] = []
    for item in fmt.replace(" ", "").split(","):
        m = _FMT_ITEM.fullmatch(item)
        if not m:
            raise ValueError(f"bad format item {item!r}")
        rep, kind, width, _ = m.groups()
        if kind == "X":
            widths.append(("X", int(rep or 1)))
        else:
            widths += [(kind, int(width))] * int(rep or 1)
    out = []
    pos = 0
    names_iter = iter(names)
    for kind, width in widths:
        field = line[pos:pos + width]
        pos += width
        if kind in ("X", "A"):
            continue
        name = next(names_iter)
        if name is None or not field.strip():
            continue
        value, tol = _val(field)
        out.append((name, value, tol))
    return out


# --- MODEL.DBG -------------------------------------------------------------

_SEMI_LABELS = {
    "Ueff": "UEFF", "SVeff": "SVEFF", "SWeff": "SWEFF",
    "UeffD": "UEFFD", "SVeffD": "SVEFFD", "SWeffD": "SWEFFD",
    "Ueff3": "UEFF3", "SVeff3": "SVEFF3", "SWeff3": "SWEFF3",
}
_AER_PCHI = {"ADJ": "ADJ", "FOPT": "FOPT", "CWRAP": "CWRAP", "CLIFT": "CLIFT",
             "D": "D", "AEROUT(ITYP)": "AEROUT"}
_PCALC_SUMMARY = {
    "PANCAKE/MEANDER COMPONENT, AERPAN(ITYP)": "AERPAN",
    "COHERENT PLUME COMPONENT,  AERPLM(ITYP)": "AERPLM",
    "MEANDER FACTOR, FRAN": "FRAN",
    "RESULTANT CONC, AERVAL(ITYP)": "AERVAL",
}
_MEANDR = {"SVEF, UEF, UMEAN:": ["SVEF", "UEF", "UMEAN"],
           "DISTR, TTRAV, TRAN:": ["DISTR", "TTRAV", "TRAN"],
           "TOTKIN, SIGRAN, FRAN:": ["TOTKIN", "SIGRAN", "FRAN"]}
_CALC_KIND_VARS = {"Stable": ["CENTER", "SZNEW", "ZRT"],
                   "Penetrated": ["HE3", "SZ3NEW", "ZRT"],
                   "Direct": ["CENTER", "SZDNEW", "ZRT"]}

# DEBOUT FORMAT 320 and 400-450 (calc1.f).
_FMT_320 = "I5,F9.1,F10.1,F8.1,F9.1,F8.1,F10.1,F8.1,F7.1,F7.1,F7.3,F6.3,F7.3,4E11.4"
_NAMES_320 = ["IREC", "XR", "YR", "ZELEV", "ZHILL", "ZFLAG", "X", "Y", "ZELEV-ZS",
              "HCRIT", "PHEE", "FOPT", "D", "CWRAP*EMIFAC", "CLIFT*EMIFAC", "AERVAL", "PRMVAL"]
_PLUME_ROWS = {
    " GAUSSIAN ": ("A10,F6.3,F9.2,F7.1,4F7.1,E11.4,2X,5F7.1,E11.4,E12.4",
                   ["PPF", "QTK", "HE", "SYAMB", "VSIGY", "SYB", "SY", "FSUBY",
                    "SZAMB", "VSIGZ", "SZB", "SZSURF", "SZ", "FSUBZ", "CHID"]),
    " DIRECT #1": ("A10,F6.3,F9.2,F7.1,4F7.1,13X,5F7.1",
                   ["PPF", "QTK*(1-PPF)", "HED1", "SYAMB", "VSIGY", "SYB", "SY",
                    "SZAD1", "VSZD1", "SZBD", "SZSURF", "SZD1"]),
    " DIRECT #2": ("A10,6X,F9.2,F7.1,4F7.1,E11.4,2X,5F7.1,E11.4,E12.4",
                   ["QTK*(1-PPF)", "HED2", "SYAMB", "VSIGY", "SYB", "SY", "FSUBYD",
                    "SZAD2", "VSZD2", "SZBD", "SZSURF", "SZD2", "FSUBZD", "CHID"]),
    " INDIRECT1": ("A10,F6.3,F9.2,F7.1,4F7.1,13X,4F7.1,F7.1",
                   ["PPF", "QTK*(1-PPF)", "HEN1", "SYAMB", "VSIGY", "SYB", "SY",
                    "SZAN1", "VSZN1", "SZBN", "SZSURF", "SZN1"]),
    " INDIRECT2": ("A10,6X,F9.2,F7.1,4F7.1,E11.4,2X,5F7.1,E11.4,E12.4",
                   ["QTK*(1-PPF)", "HEN2", "SYAMB", "VSIGY", "SYB", "SY", "FSUBYN",
                    "SZAN2", "VSZN2", "SZBN", "SZSURF", "SZN2", "FSUBZN", "CHIN"]),
    " PENETRATE": ("A10,F6.3,F9.2,F7.1,4F7.1,E11.4,2X,3F7.1,7X,F7.1,E11.4,E12.4",
                   ["PPF", "PPF*QTK", "HE3", "SYA3", "VSY3", "SYB3", "SY3", "FSUBY3",
                    "SZA3", "VSZ3", "SZB3", "SZ3", "FSUBZ3", "CHI3"]),
}
_PLUME_ROW_TAG = {" GAUSSIAN ": "GAUSSIAN", " DIRECT #1": "DIRECT1", " DIRECT #2": "DIRECT2",
                  " INDIRECT1": "INDIRECT1", " INDIRECT2": "INDIRECT2", " PENETRATE": "PENETRATE"}
_FMT_6135 = "I4,F9.1,F7.1,F7.2,F7.2,F10.1,2X,F9.1,F6.1,F9.1"
_NAMES_6135 = [None, "QS", "TS", "VS", "DS", "FB", "FM", "HS", "DHCRIT"]
_FMT_6140 = "19X,F7.1,F7.0,F8.2,2F7.2,F7.2,F8.4"
_NAMES_6140 = ["HS", "WDIR", "US", "UP", "SVS", "SWS", "TGS"]


def _kv_pairs(text: str) -> list[tuple[str, str]]:
    return re.findall(r"([A-Za-z][\w()]*)\s*=\s*(" + NUM + ")", text)


class _ModelParser:
    """State machine over MODEL.DBG; see module docstring for the key."""

    def __init__(self) -> None:
        self.raw: list[tuple] = []        # (date, isrc, irec, comp, sub, var, value, tol)
        self.date = 0
        self.isrc = 0
        self.pending_hour: list[tuple] = []
        self.block: list[tuple] | None = None
        self.block_comp = ""
        self.block_irec = 0
        self.calc_kind = ""
        self.expect: str | None = None
        self.meandr_names: list[str] | None = None

    def emit(self, sub: str, var: str, value: float, tol: float) -> None:
        if self.block is not None:
            self.block.append((sub, var, value, tol))
        else:
            self.pending_hour.append((sub, var, value, tol))

    def close_block(self) -> None:
        if self.block is not None:
            for sub, var, value, tol in self.block:
                self.raw.append((self.date, self.isrc, self.block_irec, self.block_comp,
                                 sub, var, value, tol))
        self.block = None

    def flush_hour(self) -> None:
        for sub, var, value, tol in self.pending_hour:
            self.raw.append((self.date, self.isrc, 0, "", sub, var, value, tol))
        self.pending_hour = []

    def feed(self, line: str) -> None:
        s = line.strip()
        if self.meandr_names is not None:
            if s:
                for name, tok in zip(self.meandr_names, s.split()):
                    self.emit("MEANDR", name, *_val(tok))
                self.meandr_names = None
            return
        if self.expect == "6135" and re.match(r"^\s*\d+\s+" + NUM, line):
            fields = fixed_fields(line, _FMT_6135, _NAMES_6135)
            self.isrc = int(line[:4])
            for name, value, tol in fields:
                self.pending_hour.append(("PSRDEB", name, value, tol))
            self.expect = None
            return
        if self.expect == "6140" and s and re.match(r"^" + NUM, s):
            for name, value, tol in fixed_fields(line, _FMT_6140, _NAMES_6140):
                self.pending_hour.append(("PSRDEB", name, value, tol))
            self.flush_hour()
            self.expect = None
            return
        if self.expect == "320" and re.match(r"^\s*\d+\s+" + NUM, line):
            for name, value, tol in fixed_fields(line, _FMT_320, _NAMES_320):
                if name == "IREC":
                    self.block_irec = int(value)
                else:
                    self.emit("DEBOUT", name, value, tol)
            self.expect = None
            return

        if s.startswith("--- ") and "JDAY, IHOUR" in s:
            self.close_block()
            return
        m = re.match(r"YR/MN/DY/HR:\s+(\d{8})", s)
        if m:
            self.close_block()
            self.date = int(m.group(1))
            return
        if s.startswith("SRCID:"):
            self.close_block()
            self.block = []
            self.block_comp = ""
            self.block_irec = 0
            return
        if s == "MEANDER COMPONENT":
            self.block_comp = "PAN"
            return
        if s == "COHERENT PLUME COMPONENT":
            self.block_comp = "PLM"
            return
        if s.startswith("#    (G/S)"):
            self.expect = "6135"
            return
        if s.startswith("STACK HEIGHT:"):
            self.expect = "6140"
            return
        if s.startswith("REC   REC-X"):
            self.expect = "320"
            return
        for prefix, (fmt, names) in _PLUME_ROWS.items():
            if line.startswith(prefix):
                tag = _PLUME_ROW_TAG[prefix]
                for name, value, tol in fixed_fields(line, fmt, names):
                    self.emit("DEBOUT", f"{tag}.{name}", value, tol)
                return
        if s in _MEANDR:
            self.meandr_names = _MEANDR[s]
            return
        m = re.match(r"INITIAL PLUME RISE ESTIMATE:\s+DELH =\s*(\S+) M; Uplume =\s*(\S+) M/S;"
                     r" DTHDZ =\s*(\S+)", s)
        if m:
            for name, tok in zip(["DHFAER", "UP", "TGS"], m.groups()):
                self.emit("PCALC", name, *_val(tok))
            return
        m = re.match(r"OPTH2 ITER\. #\d+: OLD DELH =\s*(\S+) M; NEW DELH =\s*(\S+) M; MET LEVEL ="
                     r"\s*(\S+) M; NEW Upl =\s*(\S+) M/S; NEW DTHDZ =\s*(\S+)", s)
        if m:
            if self.block is not None:
                sub, names = "DELTAH", ["DHPOLD", "DHP", "ZPLM", "UP", "TGP"]
            else:
                sub, names = "PCALC", ["DHFOLD", "DHFAER", "ZPLM", "UP", "TGP"]
            for name, tok in zip(names, m.groups()):
                self.emit(sub, name, *_val(tok))
            return
        m = re.match(r"Height assigned to midpoint .* = \s*(\S+) meters", s)
        if m:
            self.emit("PCALC", "ZMIDMX", *_val(m.group(1)))
            return
        m = re.match(r'For effective parameter calculations: "Final" plume rise =\s*(\S+) m;'
                     r" Distance to final rise =\s*(\S+) m", s)
        if m:
            self.emit("PCALC", "DHCRIT", *_val(m.group(1)))
            self.emit("PCALC", "XFINAL", *_val(m.group(2)))
            return
        m = re.match(r"Distance to well-mixed state =\s*(\S+) m;", s)
        if m:
            self.emit("PCALC", "XMIXED", *_val(m.group(1)))
            return
        m = re.match(r'"Effective" flow vector =\s*(\S+)', s)
        if m:
            self.emit("PCALC", "AFV", *_val(m.group(1)))
            return
        m = re.match(r"(Stable|Penetrated|Direct) plume calculation for receptor #\s*(\d+)", s)
        if m:
            self.calc_kind = m.group(1)
            self.block_irec = int(m.group(2))
            return
        m = re.match(r"Height of plume center of mass =\s*(\S+) m; Sigma-z estimate =\s*(\S+) m;"
                     r" Receptor height =\s*(\S+) m;", s)
        if m:
            for name, tok in zip(_CALC_KIND_VARS[self.calc_kind], m.groups()):
                self.emit("IBLVAL", name, *_val(tok))
            return
        m = re.match(r"New effective parameters are averaged between\s+(\S+) and\s+(\S+) meters", s)
        if m:
            self.emit("IBLVAL", "ZLO", *_val(m.group(1)))
            self.emit("IBLVAL", "ZHI", *_val(m.group(2)))
            return
        m = re.match(r"Penetration fraction =\s*(\S+)", s)
        if m:
            self.emit("IBLVAL", "PPF", *_val(m.group(1)))
            return
        if s.startswith(("Ueff", "UeffD", "Ueff3")) and "m/s" in s:
            for label, tok in _kv_pairs(s):
                self.emit("IBLVAL", _SEMI_LABELS[label], *_val(tok))
            return
        for label, var in _PCALC_SUMMARY.items():
            if s.startswith(label) and "=" in s:
                self.emit("PCALC", var, *_val(s.split("=")[-1]))
                return
        m = re.match(r"(ADJ|FOPT|CWRAP|CLIFT|D|AEROUT\(ITYP\))\s*=\s*(" + NUM + r")\s*$", s)
        if m:
            self.emit("AER_PCHI", _AER_PCHI[m.group(1)], *_val(m.group(2)))
            return

    def finish(self) -> list[tuple]:
        self.close_block()
        self.flush_hour()
        return self.raw


# --- METEOR.DBG ------------------------------------------------------------

_FMT_6115A = "1X,I4,3I3,2X,F6.1,2X,F5.1,1X,F6.3,1X,F7.3,2X,F7.1,3X,F7.3,3X,F7.4"
_NAMES_6115A = ["IYR", "IMONTH", "IDAY", "IHOUR", "ZI", "TA", "USTAR", "WSTAR",
                "OBULEN", "SFCZ0", "THSTAR"]
_FMT_6115B = "1X,F5.2,2X,F5.2,2X,F5.2,3X,F5.2,2X,F5.2,2X,F5.2,1X,F7.4"
_NAMES_6115B = ["UAVG", "SVAVG", "SWAVG", "UATZI", "SVATZI", "SWATZI", "VPTGZI"]
_FMT_6120 = "I4,F7.1,2X,F6.1,2X,F7.2,1X,F7.2,1X,F7.2,1X,F6.2,1X,F9.6"
_NAMES_6120 = [None, "GRIDHT", "GRIDWD", "GRIDWS", "GRIDSV", "GRIDSW", "GRIDPT", "GRIDTG"]


def parse_meteor(lines: Iterable[str]) -> list[tuple]:
    raw = []
    date = 0
    state = None
    for line in lines:
        s = line.strip()
        if s.startswith("YR  MO DA HR"):
            state = "A"
            continue
        if state == "A" and s:
            f = fixed_fields(line, _FMT_6115A, _NAMES_6115A)
            v = {n: x for n, x, _ in f}
            date = (int(v["IYR"]) % 100) * 1000000 + int(v["IMONTH"]) * 10000 \
                + int(v["IDAY"]) * 100 + int(v["IHOUR"])
            raw += [(date, 0, 0, "", "METDEB", n, x, t) for n, x, t in f if n not in
                    ("IYR", "IMONTH", "IDAY", "IHOUR")]
            state = "B?"
            continue
        if state == "B?" and s.startswith("(M/S)"):
            state = "B"
            continue
        if state == "B" and s:
            raw += [(date, 0, 0, "", "METDEB", n, x, t)
                    for n, x, t in fixed_fields(line, _FMT_6115B, _NAMES_6115B)]
            state = "G?"
            continue
        if state == "G?" and s.startswith("(M)"):
            state = "G"
            continue
        if state == "G":
            if not s:
                continue
            if not re.match(r"^\s*\d+\s+" + NUM, line):
                state = None
                continue
            level = int(line[:4])
            raw += [(date, 0, level, "", "METDEB", n, x, t)
                    for n, x, t in fixed_fields(line, _FMT_6120, _NAMES_6120)]
    return raw


# --- PRIME.DBG -------------------------------------------------------------

_PRIME_HOUR = {
    "HB": ("WAKE_SCALES", "HB"), "WB": ("WAKE_SCALES", "WB"), "LB": ("WAKE_SCALES", "LB"),
    "Scale length (R)": ("WAKE_SCALES", "R"),
    "Max. cavity height (HR)": ("WAKE_SCALES", "HR"),
    "Length of downwind cavity (LR)": ("WAKE_SCALES", "LR"),
    "Length of roof cavity (LC)": ("WAKE_SCALES", "LC"),
    "Buoyancy flux (FB)": ("NUMRISE", "FB"),
    "Momentum flux (FM)": ("NUMRISE", "FM"),
    "Total distance tabulated (XFIN)": ("NUMRISE", "XFIN"),
    "Final Y displacement (YFIN)": ("NUMRISE", "YFIN"),
    "Final plume height (ZFIN)": ("NUMRISE", "ZFIN"),
    "Final plume rise (DELZFIN)": ("NUMRISE", "DELZFIN"),
    "Final plume radius (RFIN)": ("NUMRISE", "RFIN"),
    "Cumul. streamline adj. (ZCUMUL)": ("NUMRISE", "ZCUMUL"),
    "Fraction of plume in CAVITY": ("NUMRISE", "FQCAV"),
}
_PRIME_REC = {"GAMFACT": ("PCALC", "GAMFACT"), "AERVAL": ("PCALC", "AERVAL"),
              "PRMVAL": ("PCALC", "PRMVAL"), "HRVAL": ("PCALC", "HRVAL")}
_PRIME_PAIRS = {"ZLO, ZHI": ["ZLO", "ZHI"], "SWEFF, SVEFF": ["SWEFF", "SVEFF"],
                "UEFF,  TGEFF": ["UEFF", "TGEFF"]}


def parse_prime(lines: Iterable[str]) -> list[tuple]:
    raw = []
    date, isrc, irec = 0, 0, 0
    pending: list[tuple] = []
    for line in lines:
        s = line.strip()
        m = re.match(r"YR/MN/DY/HR:\s+(\d{8})(?:\s+ISRC:\s+(\d+)\s+IREC:\s+(\d+))?", s)
        if m:
            date = int(m.group(1))
            if m.group(2):
                isrc, irec = int(m.group(2)), int(m.group(3))
                raw += [(date, isrc, 0, "PRIME", sub, var, v, t) for sub, var, v, t in pending]
                pending = []
            continue
        if "=" not in s:
            continue
        label, _, rhs = s.partition("=")
        label = label.strip()
        toks = re.findall(NUM, rhs)
        if label in _PRIME_HOUR and toks:
            pending.append((*_PRIME_HOUR[label], *_val(toks[0])))
        elif label in _PRIME_REC and toks:
            sub, var = _PRIME_REC[label]
            raw.append((date, isrc, irec, "PRIME", sub, var, *_val(toks[0])))
        elif label in _PRIME_PAIRS and len(toks) >= 2:
            for var, tok in zip(_PRIME_PAIRS[label], toks):
                raw.append((date, isrc, irec, "PRIME", "PRMCALC", var, *_val(tok)))
    return raw


# --- assembly --------------------------------------------------------------

def number(raw: list[tuple], file_rank: int) -> Iterator[tuple]:
    counts: dict[tuple, int] = {}
    for seq, (date, isrc, irec, comp, sub, var, value, tol) in enumerate(raw):
        base = (date, isrc, irec, comp, sub, var)
        k = counts.get(base, 0)
        counts[base] = k + 1
        yield (date, isrc, irec, file_rank, seq), Record(date, isrc, irec, comp, sub, var, k,
                                                         value, tol)


def assemble(*ranked: tuple[int, list[tuple]]) -> list[Record]:
    """Number occurrences per key and order records the way AERMOD computes them."""
    items = [item for rank, raw in ranked for item in number(raw, rank)]
    items.sort(key=lambda kv: kv[0])
    return [rec for _, rec in items]


def parse_model(lines: Iterable[str]) -> list[tuple]:
    p = _ModelParser()
    for line in lines:
        p.feed(line.rstrip("\n"))
    return p.finish()


def parse_dir(workdir: Path) -> list[Record]:
    """Parse METEOR.DBG, MODEL.DBG and PRIME.DBG (whichever exist) in a run directory."""
    ranked = []
    for rank, (name, fn) in enumerate([("METEOR.DBG", parse_meteor),
                                       ("MODEL.DBG", parse_model),
                                       ("PRIME.DBG", parse_prime)]):
        path = workdir / name
        if path.exists():
            with open(path, errors="replace") as f:
                ranked.append((rank, fn(f)))
    if not ranked:
        raise FileNotFoundError(f"no *.DBG files in {workdir}; run harness/run_ref.py --debug")
    return assemble(*ranked)
