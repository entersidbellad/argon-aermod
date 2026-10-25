"""Cement-kiln what-if scenarios on the Argon-ported AERMOD, inside Tier A scope only.

A scenario is one POINT source (the kiln stack) on flat, rural terrain with no
building downwash, on a polar receptor grid, with a year of met from an
existing Tier A EPA test case (whatif/kiln.toml). ``run`` builds the deck and
calls port/aermod_py through the same glue path as harness/run_port.py.

The port is run at 1 g/s. AERMOD's concentration is proportional to the
emission rate (plume rise depends on the stack's exit conditions, not on the
emission rate), so ``evaluate`` scales the precomputed unit-rate statistics to
any emission rate the user picks; tests/test_whatif.py checks that on the port.

Statistics follow AERMOD's own conventions, checked against ref/aermod:
- the period (annual) mean divides by the hours that are neither calm nor
  missing (output.f: IANHRS - IANCLM - IANMSG; calm/missing as metext.f CHKCLM/CHKMSG);
- the NAAQS 1-hour form is the Nth-highest daily maximum 1-hour value per
  receptor (AERMOD's 1-hr SO2/NO2 processing; days are the met file's days).
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import time
import tomllib
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import cases as catalog  # noqa: E402
import glue  # noqa: E402
import run_port  # noqa: E402
import run_ref  # noqa: E402

CONFIG_PATH = ROOT / "whatif" / "kiln.toml"
CACHE_DIR = ROOT / "whatif" / "cache"
MAX_RANK = 8
MOLAR_VOLUME_L = 24.45      # litres per mole at 25 C and 1 atm, EPA's reference conditions
SOURCE_ID = "KILN"


def load_config(path: Path = CONFIG_PATH) -> dict:
    config = tomllib.loads(Path(path).read_text())
    temps = config["grid"]["exit_temperature_k"]
    for name, mix in config["fuel_mix"].items():
        if mix["exit_temperature_k"] not in temps:
            raise ValueError(f"fuel_mix.{name}.exit_temperature_k must be one of {temps}")
        if set(mix["emission_factor"]) != set(config["pollutants"]):
            raise ValueError(f"fuel_mix.{name}.emission_factor needs {sorted(config['pollutants'])}")
    return config


@dataclass(frozen=True)
class Stack:
    height_m: float
    diameter_m: float
    temperature_k: float
    velocity_ms: float

    @property
    def key(self) -> str:
        return (f"H{self.height_m:g}_D{self.diameter_m:g}_"
                f"T{self.temperature_k:g}_V{self.velocity_ms:g}")


def grid(config: dict) -> list[Stack]:
    g = config["grid"]
    return [Stack(*map(float, v)) for v in itertools.product(
        g["stack_height_m"], g["stack_diameter_m"], g["exit_temperature_k"], g["exit_velocity_ms"])]


def on_grid(config: dict, stack: Stack) -> bool:
    return stack in set(grid(config))


def deck(stack: Stack, config: dict, *, pollutid: str = "OTHER", emission_gs: float = 1.0,
         directions: int | None = None, distances: list[float] | None = None,
         startend: str = "", extra_ou: str = "") -> str:
    """AERMOD input for one stack. The keyword set is what harness/glue.py accepts."""
    rec, met = config["receptors"], config["met"]
    n = directions or rec["directions"]
    dist = " ".join(f"{d:g}." for d in (distances or rec["distances_m"]))
    step = 360.0 / n
    return f"""CO STARTING
   TITLEONE  Cement kiln what-if {stack.key}
   MODELOPT  CONC  FLAT
   AVERTIME  1  PERIOD
   POLLUTID  {pollutid}
   RUNORNOT  RUN
   ERRORFIL  errors.out
CO FINISHED

SO STARTING
   ELEVUNIT  METERS
   LOCATION  {SOURCE_ID}  POINT  0.0  0.0  0.0
   SRCPARAM  {SOURCE_ID}  {emission_gs:g}  {stack.height_m:g}  {stack.temperature_k:g}  {stack.velocity_ms:g}  {stack.diameter_m:g}
   SRCGROUP  ALL
SO FINISHED

RE STARTING
   GRIDPOLR  POL1  STA
   GRIDPOLR  POL1  ORIG  0.0  0.0
   GRIDPOLR  POL1  DIST  {dist}
   GRIDPOLR  POL1  GDIR  {n}  {step:g}  {step:g}
   GRIDPOLR  POL1  END
RE FINISHED

ME STARTING
   SURFFILE  {met['surffile']}
   PROFFILE  {met['proffile']}
   SURFDATA  {met['surfdata']}
   UAIRDATA  {met['uairdata']}
   PROFBASE  0.0
{('   STARTEND  ' + startend) if startend else ''}
ME FINISHED

OU STARTING
   POSTFILE  1  ALL  PLOT  {catalog.POSTFILE_NAME}
{extra_ou}
OU FINISHED
"""


def met_files(config: dict) -> list[Path]:
    met_dir = catalog.EPA_DIR / "meteorology"
    return [met_dir / config["met"]["surffile"], met_dir / config["met"]["proffile"]]


def excluded_hours(project: glue.Project, met: glue.Met) -> np.ndarray:
    """Calm or missing hours inside STARTEND, as metext.f CHKCLM and CHKMSG flag them."""
    s = met.surface
    year = np.array([glue._cent(int(y)) for y in s["IYEAR"]])
    full = year * 1000000 + s["IMONTH"] * 10000 + s["IDAY"] * 100 + s["IHOUR"]
    keep = (full >= project.ISDATE) & (full <= project.IEDATE)
    u, wd, ta, L = s["UREF"], s["WDREF"], s["TA"], s["OBULEN"]
    zic, zim, ust, wst = s["ZICONV"], s["ZIMECH"], s["USTAR"], s["WSTAR"]
    calm = u == 0.0
    missing = ((u >= 90.0) | (u < 0.0) | (wd > 900.0) | (wd <= -9.0) | (ta > 900.0) | (ta <= 0.0)
               | (L < -99990.0) | ((L < 0.0) & ((zic > 90000.0) | (zic < 0.0)))
               | (zim > 90000.0) | (zim < 0.0) | (ust < 0.0) | (ust >= 9.0)
               | ((wst < 0.0) & (L < 0.0) & (L > -99990.0)))
    return (calm | missing)[keep]


def summarize(dates: np.ndarray, conc: np.ndarray, excluded: np.ndarray) -> dict:
    """Per-receptor statistics of an hourly field [hour, receptor]."""
    n_valid = int(len(dates) - excluded.sum())
    days = np.asarray(dates) // 100
    starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]])
    daily_max = np.maximum.reduceat(conc, starts, axis=0)
    ranks = -np.sort(-daily_max, axis=0)[:MAX_RANK]
    if len(ranks) < MAX_RANK:
        ranks = np.vstack([ranks, np.zeros((MAX_RANK - len(ranks), conc.shape[1]))])
    return {
        "hours": int(len(dates)), "excluded_hours": int(excluded.sum()), "days": int(len(starts)),
        "max_1h": conc.max(axis=0),
        "period": conc.sum(axis=0) / n_valid if n_valid else np.zeros(conc.shape[1]),
        "daily_max_ranks": ranks.T,                 # [receptor, rank-1]
    }


@dataclass
class Field:
    stack: Stack
    receptors: glue.Receptors
    dates: np.ndarray
    conc: np.ndarray                                # ug/m^3 per (emission_gs) g/s
    excluded: np.ndarray
    seconds: float
    port_sha256: str


def run(stack: Stack, config: dict, workdir: Path, *, package_dir: Path = run_port.PORT_DIR,
        **deck_options) -> Field:
    """Run the port on one stack; raises on any failure (the result is checked like run_port's)."""
    inp = run_ref.stage(deck(stack, config, **deck_options), met_files(config), Path(workdir))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        project = glue.load_project(inp)
    met = glue.load_met(project, inp.parent)
    setup = glue.setup_values(project, met)
    version = run_port.package_sha256(package_dir)
    port = run_port.load_port(package_dir)
    t0 = time.monotonic()
    result = run_port.check_result(port.run_case(project, met, setup), project, met)
    seconds = time.monotonic() - t0
    return Field(stack, project.receptors, result.dates, result.conc,
                 excluded_hours(project, met), seconds, version)


def _sig(values: np.ndarray) -> list:
    return [float(f"{v:.7g}") for v in np.asarray(values, dtype=float).ravel()]


def cache_record(field: Field, config: dict) -> dict:
    """What precompute stores for one stack: unit-rate statistics, receptors and provenance."""
    s = summarize(field.dates, field.conc, field.excluded)
    return {
        "stack": asdict(field.stack), "key": field.stack.key, "emission_rate_gs": 1.0,
        "port_sha256": field.port_sha256, "met": config["met"]["label"],
        "seconds": round(field.seconds, 1), "computed": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hours": s["hours"], "excluded_hours": s["excluded_hours"], "days": s["days"],
        "receptors": {"x": _sig(field.receptors.AXR), "y": _sig(field.receptors.AYR)},
        "max_1h": _sig(s["max_1h"]), "period": _sig(s["period"]),
        "daily_max_ranks": [_sig(r) for r in s["daily_max_ranks"]],
    }


# --- evaluation -------------------------------------------------------------------

def limit_ugm3(ppb: float, molecular_weight: float) -> float:
    return ppb * molecular_weight / MOLAR_VOLUME_L


def preset(config: dict, pollutant: str, fuel_mix: str) -> dict:
    """Emission rate and exit temperature a fuel-mix preset implies for a pollutant."""
    mix = config["fuel_mix"][fuel_mix]
    base = config["pollutants"][pollutant]["emission_rate_gs"]
    return {"emission_rate_gs": round(base * mix["emission_factor"][pollutant], 3),
            "exit_temperature_k": float(mix["exit_temperature_k"])}


@dataclass(frozen=True)
class Inputs:
    pollutant: str
    stack: Stack
    emission_rate_gs: float
    background_1h_ugm3: float = 0.0
    background_annual_ugm3: float = 0.0
    building_height_m: float = 0.0          # 0 = no nearby building
    building_width_m: float = 0.0
    building_distance_m: float = 0.0
    urban: bool = False
    complex_terrain: bool = False


def baseline(config: dict, pollutant: str) -> Inputs:
    d, p = config["defaults"], config["pollutants"][pollutant]
    fuel = preset(config, pollutant, d["fuel_mix"])
    return Inputs(pollutant=pollutant,
                  stack=Stack(float(d["stack_height_m"]), float(d["stack_diameter_m"]),
                              fuel["exit_temperature_k"], float(d["exit_velocity_ms"])),
                  emission_rate_gs=fuel["emission_rate_gs"],
                  background_1h_ugm3=p["background_1h_ugm3"],
                  background_annual_ugm3=p["background_annual_ugm3"])


def scope_issues(config: dict, inputs: Inputs) -> list[str]:
    """Why a scenario is outside what the Tier A port is certified for (empty = inside)."""
    issues = []
    hb, wb, dist = inputs.building_height_m, inputs.building_width_m, inputs.building_distance_m
    if hb > 0 and wb > 0:
        length = min(hb, wb)
        reach = config["scope"]["downwash_lengths"] * length
        if dist < reach:
            issues.append(
                f"A {hb:g} m tall, {wb:g} m wide building {dist:g} m from the stack is within "
                f"{config['scope']['downwash_lengths']:g}L = {reach:g} m (L = {length:g} m), so "
                "AERMOD would apply PRIME building downwash. Downwash is Tier B, which is not "
                "certified yet.")
    if inputs.urban:
        issues.append("Urban dispersion (URBANOPT) is outside Tier A scope, which is rural only.")
    if inputs.complex_terrain:
        issues.append("Elevated or complex terrain is outside Tier A scope, which is flat terrain only.")
    if inputs.pollutant not in config["pollutants"]:
        issues.append(f"Pollutant {inputs.pollutant!r} is not configured.")
    return issues


def load_cached(stack: Stack, cache_dir: Path = CACHE_DIR) -> dict | None:
    path = Path(cache_dir) / f"{stack.key}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def _receptor(record: dict, i: int) -> dict:
    x, y = record["receptors"]["x"][i], record["receptors"]["y"][i]
    return {"index": i, "x": x, "y": y, "distance_m": round(math.hypot(x, y)),
            "direction_deg": round(math.degrees(math.atan2(x, y)) % 360, 1) or 360.0}


def evaluate(config: dict, inputs: Inputs, *, cache_dir: Path = CACHE_DIR,
             current_port: str | None = None) -> dict:
    """Concentrations and NAAQS checks for one scenario, or why there are none."""
    out: dict = {"inputs": {**asdict(inputs), "stack_key": inputs.stack.key},
                 "certified": False, "status": "out_of_scope",
                 "issues": scope_issues(config, inputs)}
    if out["issues"]:
        return out
    out["status"] = "unavailable"
    if not 0 <= inputs.emission_rate_gs <= config["pollutants"][inputs.pollutant]["emission_rate_max_gs"]:
        out["issues"].append(f"Emission rate {inputs.emission_rate_gs:g} g/s is outside the slider range.")
        return out
    record = load_cached(inputs.stack, cache_dir) if on_grid(config, inputs.stack) else None
    if record is None:
        out["issues"].append(f"Stack {inputs.stack.key} has not been precomputed "
                             "(python whatif/precompute.py).")
        return out
    q = inputs.emission_rate_gs
    max_1h = np.asarray(record["max_1h"]) * q
    period = np.asarray(record["period"]) * q
    pol = config["pollutants"][inputs.pollutant]
    std = config["naaqs"][inputs.pollutant]
    rank = std["one_hour"]["rank"]
    design = np.asarray(record["daily_max_ranks"])[:, rank - 1] * q
    i_max, i_design, i_annual = int(max_1h.argmax()), int(design.argmax()), int(period.argmax())

    def check(value: float, background: float, standard: dict) -> dict:
        limit = limit_ugm3(standard["ppb"], pol["molecular_weight"])
        total = value + background
        return {"modelled_ugm3": value, "background_ugm3": background, "total_ugm3": total,
                "limit_ugm3": limit, "limit_ppb": standard["ppb"], "passes": total <= limit,
                "percent_of_limit": 100 * total / limit, "form": standard["form"],
                "cite": standard["cite"]}

    out.update({
        "certified": True, "status": "ok",
        "max_1h": {"value_ugm3": float(max_1h[i_max]), **_receptor(record, i_max)},
        "one_hour": {**check(float(design[i_design]), inputs.background_1h_ugm3, std["one_hour"]),
                     "rank": rank, **_receptor(record, i_design)},
        "annual": {**check(float(period[i_annual]), inputs.background_annual_ugm3, std["annual"]),
                   **_receptor(record, i_annual)},
        "field": {"x": record["receptors"]["x"], "y": record["receptors"]["y"],
                  "max_1h": _sig(max_1h), "one_hour": _sig(design), "annual": _sig(period)},
        "provenance": {k: record[k] for k in ("port_sha256", "met", "seconds", "computed",
                                              "hours", "excluded_hours", "days")},
    })
    out["provenance"]["port_is_current"] = (current_port is not None
                                            and record["port_sha256"] == current_port)
    return out
