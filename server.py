#!/usr/bin/env python3
"""Read-only dashboard over what the harness and agent have already written.

  python server.py [--host 127.0.0.1] [--port 8000]

Nothing here launches a model run or a test; run agent/port.py,
agent/repair_loop.py and harness/suite.py yourself, then refresh.

  GET /api/runs                 agent/runs/*: run.json plus summed reply usage
  GET /api/runs/{id}            one run: run.json, every reply's usage, result.json
  GET /api/test-results?who=    out/suite_<who>.json joined with the case catalogue
  GET /api/provenance           split.verify on port/aermod_py
  GET /api/tokens               context/tokens.json
  GET /api/commits              git log of port/aermod_py
  GET /api/certify              every certification criterion, computed now
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
import cases as catalog  # noqa: E402
import split  # noqa: E402

UI_DIR = ROOT / "ui"
RUNS_DIR = split.RUNS_DIR
PORT_DIR = split.PORT_DIR
OUT_DIR = catalog.OUT_DIR
COMPARE = ROOT / "harness" / "compare.py"
TOKENS = ROOT / "context" / "tokens.json"
NAME = re.compile(r"[A-Za-z0-9_.-]+")
USAGE_KEYS = ("total_input_tokens", "total_output_tokens", "total_thought_tokens", "total_tokens")

app = FastAPI(title="AERMOD port dashboard (read-only)")


def _json(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def _run_dir(run_id: str) -> Path:
    path = RUNS_DIR / run_id
    if not NAME.fullmatch(run_id) or run_id.startswith(".") or not path.is_dir():
        raise HTTPException(status_code=404, detail=f"no run {run_id!r}")
    return path


def _replies(run_dir: Path) -> list[dict]:
    replies = []
    for meta_path in sorted(run_dir.rglob("*.json")):
        meta = _json(meta_path)
        if isinstance(meta, dict) and {"id", "status", "usage"} <= meta.keys():
            replies.append({"path": str(meta_path.relative_to(run_dir)), "id": meta["id"],
                            "status": meta["status"], "seconds": meta.get("seconds"),
                            "usage": meta["usage"], "errors": meta.get("errors", [])})
    return replies


def _summary(run_dir: Path) -> dict:
    meta = _json(run_dir / "run.json") or {}
    replies = _replies(run_dir)
    totals = {k: sum(int(r["usage"].get(k) or 0) for r in replies) for k in USAGE_KEYS}
    return {
        "id": run_dir.name,
        "kind": meta.get("kind", "unknown"),
        "tier": meta.get("tier", "?"),
        "model": meta.get("model", "unknown"),
        "thinking": meta.get("thinking"),
        "prompt_tokens": meta.get("prompt_tokens"),
        "replies": len(replies),
        "output_tokens": totals["total_output_tokens"],
        "usage": totals,
    }


def compare_hash() -> str:
    return hashlib.sha256(COMPARE.read_bytes()).hexdigest()


@app.get("/api/runs")
def list_runs() -> list[dict]:
    if not RUNS_DIR.is_dir():
        return []
    dirs = [d for d in RUNS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
    return [_summary(d) for d in sorted(dirs, key=lambda d: d.stat().st_mtime, reverse=True)]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run_dir = _run_dir(run_id)
    return {**_summary(run_dir), "run": _json(run_dir / "run.json"),
            "reply_details": _replies(run_dir), "result": _json(run_dir / "result.json")}


@app.get("/api/test-results")
def test_results(who: str = "port") -> dict:
    if not NAME.fullmatch(who):
        raise HTTPException(status_code=400, detail="who must be a plain name")
    suite = _json(OUT_DIR / f"suite_{who}.json")
    results = {}
    for r in (suite or {}).get("results", []):
        results[r["case"]] = {
            "passes": r["passes"],
            "epa_pass": r.get("epa", {}).get("passes"),
            "strict_pass": r.get("strict", {}).get("passes"),
            "error": r.get("error"),
        }
    current = compare_hash()
    return {
        "who": who,
        "suite_found": suite is not None,
        "suite_time": (suite or {}).get("time"),
        "compare_hash": current,
        "suite_compare_hash": (suite or {}).get("compare_sha256"),
        "hash_matches": suite is not None and suite.get("compare_sha256") == current,
        "tier_a": [c.name for c in catalog.tier_cases("A")],
        "tier_b": [c.name for c in catalog.CASES if c.tier == "B"],
        "holdout": [c.name for c in catalog.CASES if c.tier == "holdout"],
        "results": results,
    }


@app.get("/api/provenance")
def provenance() -> dict:
    files = sorted(str(p.relative_to(PORT_DIR)) for p in PORT_DIR.rglob("*.py")
                   if "__pycache__" not in p.parts) if PORT_DIR.is_dir() else []
    problems = split.verify(PORT_DIR, RUNS_DIR) if PORT_DIR.is_dir() else []
    return {"ok": not problems, "python_files": files, "problems": problems}


@app.get("/api/tokens")
def tokens() -> dict:
    return _json(TOKENS) or {}


@app.get("/api/commits")
def commits(limit: int = 50) -> list[dict]:
    out = subprocess.run(["git", "log", f"-n{max(1, min(limit, 500))}",
                          "--format=%h%x09%an%x09%aI%x09%s", "--", str(PORT_DIR)],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    keys = ("hash", "author", "date", "subject")
    return [dict(zip(keys, line.split("\t", 3))) for line in out.stdout.splitlines()]


@app.get("/api/certify")
def certify() -> dict:
    """The port is certified only if every criterion holds right now."""
    results = test_results("port")
    prov = provenance()
    scored = results["results"]

    def all_pass(names: list[str], key: str) -> tuple[bool, str]:
        failing = [n for n in names if scored.get(n, {}).get(key) is not True]
        return not failing, "all pass" if not failing else "not passing: " + ", ".join(failing)

    criteria = [
        ("suite_found", results["suite_found"],
         f"out/suite_port.json from {results['suite_time']}" if results["suite_found"]
         else "run python harness/suite.py --who port --tier all"),
        ("compare_frozen", results["hash_matches"],
         f"suite scored with {results['suite_compare_hash']}, compare.py is now "
         f"{results['compare_hash']}"),
        ("tier_a_epa", *all_pass(results["tier_a"], "epa_pass")),
        ("tier_a_strict", *all_pass(results["tier_a"], "strict_pass")),
        ("port_exists", bool(prov["python_files"]),
         f"{len(prov['python_files'])} Python files in port/aermod_py"),
        ("provenance", prov["ok"],
         "every file came from a recorded model reply" if prov["ok"]
         else "; ".join(prov["problems"][:5])),
    ]
    return {
        "certified": all(ok for _, ok, _ in criteria),
        "criteria": [{"name": n, "ok": bool(ok), "detail": d} for n, ok, d in criteria],
    }


if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
