#!/usr/bin/env python3
"""Read-only dashboard over what the harness and agent have already written.

  python server.py [--host 127.0.0.1] [--port 8000] [--root CHECKOUT]

``--root`` reads the run artifacts, port and results of another checkout (for
example one of ``argon/port-tier-a``) with this checkout's code. Nothing here
launches a model run or a test; run agent/port.py, agent/repair_loop.py and
harness/suite.py yourself, then refresh.

A run is any folder under agent/runs/ holding run.json (agent/port.py and
agent/repair_loop.py's CLI) or result.json (repair_loop.repair called directly,
e.g. agent/runs/repair_A_box/step_001); its id is that folder's path.

  GET /api/runs                 every run: metadata, Argon interactions, usage and cost
  GET /api/runs/{id}            one run, plus run.json and result.json
  GET /api/results              results/tier_*.md snapshots: case table and Argon calls
  GET /api/test-results?who=    per-case scores: out/suite_<who>.json, else the
                                results/tier_*.md snapshots, else the latest result.json
  GET /api/frozen               compare.py's digest against harness/compare.sha256, and its thresholds
  GET /api/provenance           every port file traced to its Argon interaction (split.trace)
  GET /api/tokens               context/tokens.json
  GET /api/commits              git log of port/aermod_py
  GET /api/certify              every certification criterion, computed now
  GET /api/overview             per-tier status, Argon usage, provenance and certification in one
                                summary (the header, the pipeline strip and the README's results)
  GET /api/whatif/config        what-if sliders, fuel-mix presets, NAAQS and cache coverage
  GET /api/whatif?...           baseline and scenario concentrations from whatif/cache
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "whatif"))
import cases as catalog  # noqa: E402
import compare  # noqa: E402
import run_port  # noqa: E402
import scenario as whatif  # noqa: E402
import split  # noqa: E402

UI_DIR = ROOT / "ui"
NAME = re.compile(r"[A-Za-z0-9_.-]+")
USAGE_KEYS = ("total_input_tokens", "total_output_tokens", "total_thought_tokens", "total_tokens")

DATA_ROOT = ROOT
RUNS_DIR = split.RUNS_DIR
PORT_DIR = split.PORT_DIR
OUT_DIR = catalog.OUT_DIR
RESULTS_DIR = ROOT / "results"
COMPARE = ROOT / "harness" / "compare.py"
APPROVED = ROOT / "harness" / "compare.sha256"
TOKENS = ROOT / "context" / "tokens.json"
WHATIF_CONFIG = whatif.CONFIG_PATH
WHATIF_CACHE = whatif.CACHE_DIR


def configure(root: Path) -> None:
    """Read artifacts from another checkout."""
    global DATA_ROOT, RUNS_DIR, PORT_DIR, OUT_DIR, RESULTS_DIR, COMPARE, APPROVED, TOKENS
    global WHATIF_CONFIG, WHATIF_CACHE
    DATA_ROOT = root.resolve()
    RUNS_DIR = DATA_ROOT / "agent" / "runs"
    PORT_DIR = DATA_ROOT / "port" / "aermod_py"
    OUT_DIR = DATA_ROOT / "out"
    RESULTS_DIR = DATA_ROOT / "results"
    COMPARE = DATA_ROOT / "harness" / "compare.py"
    APPROVED = DATA_ROOT / "harness" / "compare.sha256"
    TOKENS = DATA_ROOT / "context" / "tokens.json"
    if (DATA_ROOT / "whatif" / "kiln.toml").is_file():
        WHATIF_CONFIG = DATA_ROOT / "whatif" / "kiln.toml"
        WHATIF_CACHE = DATA_ROOT / "whatif" / "cache"


app = FastAPI(title="AERMOD port dashboard (read-only)")


def _json(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def _run_dirs() -> list[Path]:
    if not RUNS_DIR.is_dir():
        return []
    found = {p.parent for name in ("run.json", "result.json") for p in RUNS_DIR.rglob(name)}
    found = {d for d in found
             if not any(part.startswith(".") for part in d.relative_to(RUNS_DIR).parts)}
    return sorted(found, key=lambda d: d.relative_to(RUNS_DIR).as_posix())


def _run_id(run_dir: Path) -> str:
    return run_dir.relative_to(RUNS_DIR).as_posix()


def _run_dir(run_id: str) -> Path:
    parts = run_id.split("/")
    if all(NAME.fullmatch(p) and not p.startswith(".") for p in parts):
        path = RUNS_DIR.joinpath(*parts)
        if path in _run_dirs():
            return path
    raise HTTPException(status_code=404, detail=f"no run {run_id!r}")


# --- results/tier_*.md --------------------------------------------------------

def _md_tables(text: str) -> list[list[dict]]:
    """Every pipe table in a markdown file, as rows keyed by lower-cased header."""
    tables, block = [], []
    for line in text.splitlines() + [""]:
        if line.lstrip().startswith("|"):
            block.append([c.strip() for c in line.strip().strip("|").split("|")])
            continue
        if len(block) > 2:
            header = [h.lower() for h in block[0]]
            tables.append([dict(zip(header, row)) for row in block[2:]])
        block = []
    return tables


def _col(row: dict, prefix: str) -> str:
    return next((v for k, v in row.items() if k.startswith(prefix)), "")


def _num(text: str) -> float | None:
    try:
        return float(text.strip("`*$% ").replace(",", ""))
    except ValueError:
        return None


def _snapshot_case(row: dict) -> dict:
    passes = row.get("result", "").upper() == "PASS"
    slopes = [_num(s) for s in _col(row, "slope").split("/")]
    slopes += [None] * (3 - len(slopes))
    zero = _num(_col(row, "zero"))
    return {
        "passes": passes, "role": row.get("role"),
        # A PASS row means harness/compare.py's EPA and strict rules both held.
        "epa_pass": True if passes else None, "strict_pass": True if passes else None,
        "error": None, "slope": slopes[0], "slope_ols": slopes[1], "mean_ratio": slopes[2],
        "p99_rel_err": _num(_col(row, "p99")),
        "zero_agreement": zero / 100 if zero is not None else None,
        "h4h_fails": _col(row, "h4h") or None, "summary": None,
    }


def _snapshot(path: Path) -> dict:
    text = path.read_text()
    cases, calls = {}, []
    for table in _md_tables(text):
        if "case" in table[0] and "result" in table[0]:
            cases.update({r["case"]: _snapshot_case(r) for r in table})
        elif "interaction id" in table[0]:
            for r in table:
                if r.get("step", "").startswith("**"):
                    continue
                calls.append({
                    "step": r.get("step"), "interaction_id": r["interaction id"].strip("`"),
                    "packet_tokens": _num(_col(r, "packet")),
                    "billed_input_tokens": _num(_col(r, "billed input")),
                    "output_tokens": _num(_col(r, "output")),
                    "thought_tokens": _num(_col(r, "thinking")),
                    "cost_usd": _num(_col(r, "cost")),
                })
    title = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    digest = re.search(r"sha256\s+`([0-9a-f]{64})`", text)
    scored = re.search(r"Scored\s+(.+?)\s+on harness\s+`([0-9a-f]+)`", text)
    prices = re.search(r"^Prices:\s*(.+)$", text, re.MULTILINE)
    return {
        "path": f"results/{path.name}",
        "title": title.group(1) if title else path.stem,
        "compare_sha256": digest.group(1) if digest else None,
        "scored": scored.group(1) if scored else None,
        "harness": scored.group(2) if scored else None,
        "prices": prices.group(1) if prices else None,
        "cases": cases, "calls": calls,
    }


@app.get("/api/results")
def results_snapshots() -> list[dict]:
    if not RESULTS_DIR.is_dir():
        return []
    return [_snapshot(p) for p in sorted(RESULTS_DIR.glob("tier_*.md"))]


# --- runs -----------------------------------------------------------------------

def _by_interaction(run_dir: Path, filename: str) -> dict[str, dict]:
    """files.json entries or decision.json records under run_dir, keyed by interaction id."""
    out: dict[str, dict] = {}
    for path in sorted(run_dir.rglob(filename)):
        data = _json(path)
        for entry in data if isinstance(data, list) else [data]:
            if isinstance(entry, dict) and entry.get("interaction_id"):
                out.setdefault(entry["interaction_id"], entry)
    return out


def _interactions(run_dir: Path, costs: dict[str, float | None]) -> list[dict]:
    manifests = _by_interaction(run_dir, split.MANIFEST)
    decisions = _by_interaction(run_dir, "decision.json")
    out = []
    for meta_path in sorted(run_dir.rglob("*.json")):
        meta = _json(meta_path)
        if not (isinstance(meta, dict) and {"id", "status", "usage"} <= meta.keys()):
            continue
        entry, decision = manifests.get(meta["id"], {}), decisions.get(meta["id"])
        out.append({
            "path": meta_path.relative_to(run_dir).as_posix(), "id": meta["id"],
            "status": meta["status"], "seconds": meta.get("seconds"),
            "usage": meta["usage"], "errors": meta.get("errors", []),
            "step": entry.get("step") or (decision or {}).get("mode"),
            "iteration": entry.get("iteration", (decision or {}).get("iteration")),
            "files": sorted(entry.get("files", {})),
            "decision": {k: decision.get(k) for k in ("problem", "hypothesis", "accepted", "reason")}
            if decision else None,
            "cost_usd": costs.get(meta["id"]),
        })
    return out


def _tier_of(case_names) -> str | None:
    tiers = {c.tier for c in catalog.CASES if c.name in set(case_names)}
    return "B" if "B" in tiers else "A" if "A" in tiers else None


def _summary(run_dir: Path, costs: dict[str, float | None]) -> dict:
    meta = _json(run_dir / "run.json") or {}
    result = _json(run_dir / "result.json") or {}
    interactions = _interactions(run_dir, costs)
    totals = {k: sum(int(i["usage"].get(k) or 0) for i in interactions) for k in USAGE_KEYS}
    attempts = result.get("attempts", [])
    known = [i["cost_usd"] for i in interactions if i["cost_usd"] is not None]
    final = result.get("final", {})
    return {
        "id": _run_id(run_dir),
        "kind": meta.get("kind") or ("repair" if "attempts" in result else
                                     next((i["step"] for i in interactions if i["step"]), None)),
        "tier": meta.get("tier") or _tier_of(final),
        "model": meta.get("model"),
        "thinking": meta.get("thinking"),
        "prompt_tokens": meta.get("prompt_tokens"),
        "token_method": meta.get("token_method"),
        "fortran_pack": meta.get("fortran_pack"),
        "expected_input_multiplier": meta.get("expected_input_multiplier"),
        "replies": len(interactions),
        "interactions": interactions,
        "output_tokens": totals["total_output_tokens"],
        "usage": totals,
        "cost_usd": sum(known) if known else result.get("spent_usd"),
        "cost_complete": bool(interactions) and len(known) == len(interactions),
        "iterations": result.get("iterations"),
        "patches_kept": sum(1 for a in attempts if a.get("accepted")) if attempts else None,
        "cases_passing": sum(1 for s in final.values() if s.get("passes")) if final else None,
        "cases_scored": len(final) if final else None,
        "stop_reason": result.get("stop_reason"),
        "spent_usd": result.get("spent_usd"),
    }


def _costs() -> dict[str, float | None]:
    return {c["interaction_id"]: c["cost_usd"] for s in results_snapshots() for c in s["calls"]}


@app.get("/api/runs")
def list_runs() -> list[dict]:
    costs = _costs()
    return [_summary(d, costs) for d in _run_dirs()]


@app.get("/api/runs/{run_id:path}")
def get_run(run_id: str) -> dict:
    run_dir = _run_dir(run_id)
    return {**_summary(run_dir, _costs()), "run": _json(run_dir / "run.json"),
            "result": _json(run_dir / "result.json")}


# --- scores, frozen compare.py, provenance ----------------------------------------

def compare_hash() -> str:
    return hashlib.sha256(COMPARE.read_bytes()).hexdigest()


def approved_hash() -> str | None:
    return APPROVED.read_text().split()[0] if APPROVED.is_file() else None


def port_hash() -> str | None:
    """Digest of port/aermod_py as harness/run_port.py stamps it, or None with no port."""
    return run_port.package_sha256(PORT_DIR) if (PORT_DIR / "__init__.py").is_file() else None


def _suite_row(r: dict) -> dict:
    epa, strict = r.get("epa", {}), r.get("strict", {})
    return {
        "passes": r["passes"], "epa_pass": epa.get("passes"), "strict_pass": strict.get("passes"),
        "error": r.get("error"), "slope": epa.get("slope"), "slope_ols": epa.get("slope_ols"),
        "mean_ratio": epa.get("mean_ratio"), "p99_rel_err": strict.get("p99_rel_err"),
        "zero_agreement": strict.get("zero_agreement"),
        "h4h_max_rel_diff": strict.get("h4h_max_rel_diff"),
        "h4h_fails": f"{strict['h4h_n_fail']}/{strict['h4h_n_receptors']}"
        if "h4h_n_fail" in strict else None,
        "port_sha256": r.get("port_sha256"), "summary": None,
    }


def _repair_rows(result: dict) -> dict:
    """Scores the repair loop saved (harness/compare.py rows), when nothing better exists."""
    rows = {}
    for s in list(result.get("final", {}).values()) + list(result.get("holdout", {}).values()):
        rows[s["case"]] = {"passes": s["passes"], "epa_pass": None, "strict_pass": None,
                           "error": s.get("error") or None, "summary": s.get("summary") or None}
    return rows


def _scored_port(suite: dict, names: list[str]) -> str | None:
    """The one port version every named case was scored with, else the suite's own stamp."""
    stamps = {r.get("port_sha256") for r in suite.get("results", []) if r.get("case") in names}
    if len(stamps) == 1 and None not in stamps:
        return stamps.pop()
    return None if len(stamps) > 1 else suite.get("port_sha256")


def _holdout_tier(case: catalog.Case) -> str:
    """The tier a holdout tests: B if its deck carries PRIME building data, else A."""
    deck = case.inp.read_text() if case.inp.is_file() else ""
    return "B" if re.search(r"^\s*(SO\s+)?BUILDHGT\b", deck, re.MULTILINE) else "A"


def _case_info() -> dict:
    return {c.name: {"tier": c.tier, "tests_tier": _holdout_tier(c) if c.tier == "holdout" else c.tier,
                     "reference": "EPA POSTFILE" if c.epa_postfile else "our gfortran build",
                     "notes": c.notes}
            for c in catalog.CASES}


@app.get("/api/test-results")
def test_results(who: str = "port") -> dict:
    return _scores(who, use_suite=True)


def _scores(who: str, use_suite: bool) -> dict:
    """Per-case scores; ``use_suite=False`` ignores this machine's out/ and reads committed files."""
    if not NAME.fullmatch(who):
        raise HTTPException(status_code=400, detail="who must be a plain name")
    tier_a = [c.name for c in catalog.tier_cases("A")]
    suite = _json(OUT_DIR / f"suite_{who}.json") if use_suite else None
    snapshots = results_snapshots() if who == "port" else []
    scored_with, scored_at = None, None
    if suite is not None:
        source = f"out/suite_{who}.json"
        results = {r["case"]: _suite_row(r) for r in suite.get("results", [])}
        scored_with, scored_at = suite.get("compare_sha256"), suite.get("time")
    elif any(s["cases"] for s in snapshots):
        used = [s for s in snapshots if s["cases"]]
        source = ", ".join(s["path"] for s in used)
        results = {name: row for s in used for name, row in s["cases"].items()}
        digests = {s["compare_sha256"] for s in used}
        scored_with = digests.pop() if len(digests) == 1 else None
        scored_at = "; ".join(f"{s['scored']} on harness {s['harness']}" for s in used if s["scored"])
    else:
        latest = next((d for d in reversed(_run_dirs())
                       if (_json(d / "result.json") or {}).get("final")), None)
        source = f"agent/runs/{_run_id(latest)}/result.json" if latest else None
        results = _repair_rows(_json(latest / "result.json")) if latest else {}
    current, port_now = compare_hash(), port_hash()
    scored_port = _scored_port(suite, tier_a) if suite is not None else None
    return {
        "who": who,
        "source": source,
        "suite_found": suite is not None,
        "suite_time": scored_at,
        "compare_hash": current,
        "suite_compare_hash": scored_with,
        "hash_matches": scored_with == current,
        "port_hash": port_now,
        "suite_port_hash": scored_port,
        "port_matches": port_now is not None and scored_port == port_now,
        "tier_a": tier_a,
        "tier_b": [c.name for c in catalog.CASES if c.tier == "B"],
        "holdout": [c.name for c in catalog.CASES if c.tier == "holdout"],
        "cases": _case_info(),
        "results": results,
    }


@app.get("/api/frozen")
def frozen() -> dict:
    current, approved = compare_hash(), approved_hash()
    return {"compare_hash": current, "approved_hash": approved,
            "matches": approved is not None and current == approved,
            "rules": {"slope_tolerance": compare.SLOPE_TOL,
                      "zero_agreement_min": compare.ZERO_AGREEMENT_MIN,
                      "relative_tolerance": compare.REL_TOL,
                      "significant_fraction": compare.SIGNIFICANT_FRACTION,
                      "percentile": compare.PERCENTILE}}


@app.get("/api/provenance")
def provenance() -> dict:
    files = split.trace(PORT_DIR, RUNS_DIR) if PORT_DIR.is_dir() and RUNS_DIR.is_dir() else []
    problems = [f"{t['file']}: {t['problem']}" for t in files if t["problem"]]
    return {"ok": not problems, "python_files": [t["file"] for t in files if t["file"].endswith(".py")],
            "files": files, "problems": problems,
            "interactions": sorted({t["interaction_id"] for t in files if t["interaction_id"]})}


@app.get("/api/tokens")
def tokens() -> dict:
    return _json(TOKENS) or {}


@app.get("/api/commits")
def commits(limit: int = 50) -> list[dict]:
    out = subprocess.run(["git", "log", f"-n{max(1, min(limit, 500))}",
                          "--format=%h%x09%an%x09%aI%x09%s", "--", str(PORT_DIR)],
                         cwd=DATA_ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    keys = ("hash", "author", "date", "subject")
    return [dict(zip(keys, line.split("\t", 3))) for line in out.stdout.splitlines()]


@app.get("/api/certify")
def certify() -> dict:
    """The port is certified only if every criterion holds right now."""
    results = test_results("port")
    prov = provenance()
    lock = frozen()
    scored = results["results"]

    def all_pass(names: list[str], key: str) -> tuple[bool, str]:
        failing = [n for n in names if scored.get(n, {}).get(key) is not True]
        return not failing, "all pass" if not failing else "not passing: " + ", ".join(failing)

    criteria = [
        ("suite_found", results["suite_found"],
         f"out/suite_port.json from {results['suite_time']}" if results["suite_found"]
         else "run make suite-port to score this checkout's port (shown scores come from "
              f"{results['source'] or 'nowhere'}, which does not record the port version)"),
        ("compare_approved", lock["matches"],
         f"compare.py {lock['compare_hash']}, approved {lock['approved_hash']}"),
        ("compare_frozen", results["hash_matches"],
         f"scored with {results['suite_compare_hash']}, compare.py is now "
         f"{results['compare_hash']}"),
        ("scored_this_port", results["port_matches"],
         f"tier A scored port {results['suite_port_hash']}, port/aermod_py is now "
         f"{results['port_hash']}"),
        ("tier_a_epa", *all_pass(results["tier_a"], "epa_pass")),
        ("tier_a_strict", *all_pass(results["tier_a"], "strict_pass")),
        ("port_exists", bool(prov["python_files"]),
         f"{len(prov['python_files'])} Python files in port/aermod_py"),
        ("provenance", prov["ok"],
         f"every file traced to {len(prov['interactions'])} Argon interaction(s)" if prov["ok"]
         else "; ".join(prov["problems"][:5])),
    ]
    return {
        "certified": all(ok for _, ok, _ in criteria),
        "criteria": [{"name": n, "ok": bool(ok), "detail": d} for n, ok, d in criteria],
    }


def _tally(names: list[str], scored: dict) -> dict:
    rows = [scored.get(n) for n in names]
    return {"cases": names, "scored": sum(r is not None for r in rows),
            "passing": sum(1 for r in rows if r and r.get("passes") is True)}


def _tier_status(tier: str, training: dict, holdout: dict) -> str:
    """passing when every case of the tier passes. Tier B stays in_progress until then,
    because its PRIME port is still being written; tier A failing means a regression."""
    cases = len(training["cases"]) + len(holdout["cases"])
    if cases and training["passing"] + holdout["passing"] == cases:
        return "passing"
    if tier == "B":
        return "in_progress"
    return "failing" if training["scored"] + holdout["scored"] else "not_scored"


def summary(use_suite: bool = True) -> dict:
    """Everything the header, the pipeline strip and the README's results block show.

    ``use_suite=False`` reads only committed files (results/, agent/runs/, port/), not
    this machine's out/suite_port.json, and skips certification, which needs out/.
    """
    scores = _scores("port", use_suite)
    info, scored = scores["cases"], scores["results"]
    tiers = {}
    for tier in ("A", "B"):
        training = _tally([n for n, c in info.items() if c["tier"] == tier], scored)
        holdout = _tally([n for n, c in info.items()
                          if c["tier"] == "holdout" and c["tests_tier"] == tier], scored)
        tiers[tier] = {"training": training, "holdout": holdout,
                       "status": _tier_status(tier, training, holdout)}
    runs = list_runs()
    interactions = [i for r in runs for i in r["interactions"]]
    known = [i["cost_usd"] for i in interactions if i["cost_usd"] is not None]
    prov = provenance()
    certified = certify()["certified"] if use_suite else None
    suite = _json(OUT_DIR / "suite_port.json") if certified else None
    tier_b = tiers["B"]["training"]["cases"] + tiers["B"]["holdout"]["cases"]
    b_scored_here = suite is not None and port_hash() is not None \
        and _scored_port(suite, tier_b) == port_hash()
    return {
        "tiers": tiers,
        "scores": {k: scores[k] for k in ("source", "suite_found", "suite_time", "hash_matches",
                                          "port_matches")},
        "argon": {
            "runs": [{k: r[k] for k in ("id", "kind", "tier", "model", "thinking", "replies",
                                        "prompt_tokens", "usage", "cost_usd", "cost_complete")}
                     for r in runs],
            "interactions": len(interactions),
            "usage": {k: sum(int(i["usage"].get(k) or 0) for i in interactions) for k in USAGE_KEYS},
            "cost_usd": sum(known) if known else None,
            "cost_complete": bool(interactions) and len(known) == len(interactions),
            "prices": [{"path": s["path"], "prices": s["prices"]}
                       for s in results_snapshots() if s["prices"]],
        },
        "provenance": {"ok": prov["ok"], "python_files": len(prov["python_files"]),
                       "interactions": len(prov["interactions"])},
        "compare_frozen": frozen()["matches"],
        "tokens": tokens(),
        "port_sha256": port_hash(),
        "certified": certified,
        # Certification criteria cover Tier A; Tier B joins once every Tier B case passes
        # in the same suite, scored on this exact port.
        "certified_tiers": (["A"] + (["B"] if tiers["B"]["status"] == "passing" and b_scored_here
                                     else [])) if certified else [],
    }


@app.get("/api/overview")
def overview() -> dict:
    return summary(use_suite=True)


# --- what-if (whatif/) ------------------------------------------------------------

@app.get("/api/whatif/config")
def whatif_config() -> dict:
    """Sliders, presets, standards and baselines for the What-if screen."""
    config = whatif.load_config(WHATIF_CONFIG)
    stacks = whatif.grid(config)
    cached = [s.key for s in stacks if whatif.load_cached(s, WHATIF_CACHE)]
    limits = {p: {avg: {**std, "limit_ugm3": whatif.limit_ugm3(
                  std["ppb"], config["pollutants"][p]["molecular_weight"])}
                  for avg, std in config["naaqs"][p].items()}
              for p in config["pollutants"]}
    return {
        "title": config["title"], "met": config["met"], "receptors": config["receptors"],
        "grid": config["grid"], "defaults": config["defaults"],
        "pollutants": config["pollutants"], "fuel_mix": config["fuel_mix"], "naaqs": limits,
        "scope": config["scope"],
        "presets": {p: {m: whatif.preset(config, p, m) for m in config["fuel_mix"]}
                    for p in config["pollutants"]},
        "stacks": len(stacks), "cached": len(cached), "port_sha256": port_hash(),
        "config_path": "whatif/kiln.toml",
    }


@app.get("/api/whatif")
def whatif_scenario(pollutant: str, height: float, diameter: float, temperature: float,
                    velocity: float, emission: float, background_1h: float = 0.0,
                    background_annual: float = 0.0, building_height: float = 0.0,
                    building_width: float = 0.0, building_distance: float = 0.0,
                    urban: bool = False, complex_terrain: bool = False) -> dict:
    """Baseline (config defaults) and the requested scenario, from precomputed port runs."""
    config = whatif.load_config(WHATIF_CONFIG)
    if pollutant not in config["pollutants"]:
        raise HTTPException(status_code=400, detail=f"pollutant must be one of {sorted(config['pollutants'])}")
    inputs = whatif.Inputs(
        pollutant=pollutant, stack=whatif.Stack(height, diameter, temperature, velocity),
        emission_rate_gs=emission, background_1h_ugm3=background_1h,
        background_annual_ugm3=background_annual, building_height_m=building_height,
        building_width_m=building_width, building_distance_m=building_distance,
        urban=urban, complex_terrain=complex_terrain)
    port_now = port_hash()
    return {
        "baseline": whatif.evaluate(config, whatif.baseline(config, pollutant),
                                    cache_dir=WHATIF_CACHE, current_port=port_now),
        "scenario": whatif.evaluate(config, inputs, cache_dir=WHATIF_CACHE, current_port=port_now),
    }


if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--root", type=Path, help="read artifacts from this checkout")
    args = ap.parse_args()
    if args.root:
        configure(args.root)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
