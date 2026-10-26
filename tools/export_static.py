#!/usr/bin/env python3
"""Export the dashboard as a static, read-only site (Vercel or any static host).

  python tools/export_static.py [--out site]     # or: make export-static
  python tools/export_static.py --check          # fail if site/ is stale
  python tools/export_static.py --fetch-ci [RUN] # refresh results/ci_port_suite.json (needs gh)

Drives server.py's own app in-process and writes every response the UI fetches
as JSON under <out>/data/, next to a copy of ui/. Nothing is computed when the
site is served: the What-if tab offers the precomputed fuel-mix presets only.

Scores come from results/ci_port_suite.json, the out/suite_port.json that the
port-suite job of a green main CI run uploaded. The export hands it to
server.certify() as this checkout's out/suite_port.json, so the site is
certified only if every criterion holds, including that CI scored exactly the
committed port/aermod_py.
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server  # noqa: E402

SNAPSHOT_NAME = "results/ci_port_suite.json"
SNAPSHOT = ROOT / SNAPSHOT_NAME
SITE = ROOT / "site"
UI_FILES = ("index.html", "app.css", "app.js")
APP_SCRIPT = '<script src="app.js"></script>'
COMMITS = 20  # the How it was built tab asks for this many
SECRETS = re.compile(r"AIza[0-9A-Za-z_-]{30,}|ghp_[0-9A-Za-z]{30,}|github_pat_\w{30,}|sk-[0-9A-Za-z]{30,}"
                     r"|GEMINI_API_KEY\s*[=:]\s*\S")


def _dump(data) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def _ci_label(ci: dict | None, port_now: str | None, certified: bool) -> str:
    if ci is None:
        return f"Not certified: no CI snapshot ({SNAPSHOT_NAME})"
    run = f"CI run {ci['run_id']} ({ci['completed_at'][:10]}) on commit {ci['commit'][:7]}"
    if ci["suite"].get("port_sha256") != port_now:
        return (f"Not certified: {run} scored port {str(ci['suite'].get('port_sha256'))[:12]}, "
                f"but the committed port/aermod_py is {str(port_now)[:12]}")
    return f"Certified by {run}" if certified else f"Not certified: {run} fails a criterion"


def build() -> tuple[dict[str, str], dict]:
    """Every file of the static site keyed by its path under the site root, and the
    certification metadata the site shows (also written to data/static.js)."""
    snapshot = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.is_file() else None
    saved_out = server.OUT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        if snapshot:
            (Path(tmp) / "suite_port.json").write_text(json.dumps(snapshot["suite"]))
        server.OUT_DIR = Path(tmp)
        try:
            client = TestClient(server.app)

            def get(url: str):
                r = client.get(url)
                r.raise_for_status()
                return r.json()

            data = {name: get(f"/api/{name}") for name in
                    ("overview", "frozen", "runs", "results", "tokens", "test-results",
                     "provenance", "certify", "whatif/config")}
            data["commits"] = get(f"/api/commits?limit={COMMITS}")
            for run in data["runs"]:
                data[f"runs/{run['id']}"] = get(f"/api/runs/{run['id']}")
            config = server.whatif.load_config(server.WHATIF_CONFIG)
            d = config["defaults"]
            for pollutant, p in config["pollutants"].items():
                for fuel in config["fuel_mix"]:
                    preset = server.whatif.preset(config, pollutant, fuel)
                    data[f"whatif/{pollutant}/{fuel}"] = get("/api/whatif?" + "&".join(
                        f"{k}={v}" for k, v in {
                            "pollutant": pollutant, "height": float(d["stack_height_m"]),
                            "diameter": float(d["stack_diameter_m"]),
                            "temperature": preset["exit_temperature_k"],
                            "velocity": float(d["exit_velocity_ms"]),
                            "emission": preset["emission_rate_gs"],
                            "background_1h": p["background_1h_ugm3"],
                            "background_annual": p["background_annual_ugm3"]}.items()))
        finally:
            server.OUT_DIR = saved_out

    # The suite the export scored from is the CI snapshot, not anything under out/.
    for name in ("overview", "test-results", "certify"):
        data[name] = json.loads(json.dumps(data[name]).replace("out/suite_port.json", SNAPSHOT_NAME))

    ci, port_now = snapshot, data["overview"]["port_sha256"]
    certified = bool(data["overview"]["certified"])
    meta = {
        "ci": {**{k: ci[k] for k in ("run_id", "run_url", "commit", "completed_at")},
               "port_sha256": ci["suite"].get("port_sha256"),
               "compare_sha256": ci["suite"].get("compare_sha256")} if ci else None,
        "port_sha256": port_now,
        "port_matches": bool(ci) and ci["suite"].get("port_sha256") == port_now,
        "certified": certified,
        "label": _ci_label(ci, port_now, certified),
    }

    index = (server.UI_DIR / "index.html").read_text()
    if APP_SCRIPT not in index:
        raise SystemExit(f"ui/index.html no longer loads app.js with {APP_SCRIPT}")
    files = {"index.html": index.replace(APP_SCRIPT, f'<script src="data/static.js"></script>\n{APP_SCRIPT}'),
             "app.css": (server.UI_DIR / "app.css").read_text(),
             "app.js": (server.UI_DIR / "app.js").read_text(),
             "data/static.js": "// Written by tools/export_static.py: app.js reads data/*.json instead of server.py.\n"
                               f"window.AERMOD_STATIC = {json.dumps(meta, indent=1)};\n"}
    files.update({f"data/{name}.json": _dump(body) for name, body in data.items()})
    leaks = [path for path, text in files.items() if SECRETS.search(text)]
    if leaks:
        raise SystemExit(f"refusing to export, secret-like strings in: {', '.join(leaks)}")
    return files, meta


def write(files: dict[str, str], out: Path) -> None:
    shutil.rmtree(out / "data", ignore_errors=True)
    for rel, text in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def stale(out: Path) -> list[str]:
    """A line per file under out that is missing, changed or extra against a fresh export,
    each followed by the start of its diff."""
    want = build()[0]
    have = {p.relative_to(out).as_posix(): p.read_text() for p in out.rglob("*") if p.is_file()} \
        if out.is_dir() else {}
    report = []
    for rel in sorted(have.keys() | want.keys()):
        if have.get(rel) != want.get(rel):
            report.append(f"stale: {out.name}/{rel}")
            diff = difflib.unified_diff((have.get(rel) or "").splitlines(), (want.get(rel) or "").splitlines(),
                                        "committed", "fresh", n=1, lineterm="")
            report += [f"    {line}" for line in itertools.islice(diff, 12)]
    return report


def fetch_ci(run_id: str | None) -> None:
    """Replace the snapshot with suite_port.json from a green main CI run (default: the latest)."""
    def gh(*args: str) -> str:
        return subprocess.run(["gh", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout

    if run_id is None:
        runs = json.loads(gh("run", "list", "--branch", "main", "--workflow", "ci.yml", "--status",
                             "success", "--limit", "1", "--json", "databaseId"))
        if not runs:
            raise SystemExit("no successful CI run on main")
        run_id = str(runs[0]["databaseId"])
    run = json.loads(gh("run", "view", run_id, "--json", "url,headSha,headBranch,jobs"))
    job = next((j for j in run["jobs"] if j["name"] == "port-suite"), None)
    if run["headBranch"] != "main" or not job or job["conclusion"] != "success":
        raise SystemExit(f"run {run_id} is not a green port-suite run on main")
    with tempfile.TemporaryDirectory() as tmp:
        gh("run", "download", run_id, "-n", "suite_port", "-D", tmp)
        suite = json.loads((Path(tmp) / "suite_port.json").read_text())
    SNAPSHOT.write_text(_dump({
        "about": "out/suite_port.json uploaded by the port-suite job of a green main CI run "
                 "(tools/export_static.py --fetch-ci); the static site scores and certifies from it.",
        "run_id": int(run_id), "run_url": run["url"], "workflow": ".github/workflows/ci.yml",
        "job": "port-suite", "commit": run["headSha"], "completed_at": job["completedAt"],
        "suite": suite,
    }))
    print(f"{SNAPSHOT_NAME}: run {run_id}, commit {run['headSha'][:7]}, "
          f"port {suite.get('port_sha256', '')[:12]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=SITE)
    ap.add_argument("--check", action="store_true", help="fail if --out differs from a fresh export")
    ap.add_argument("--fetch-ci", nargs="?", const="", metavar="RUN_ID",
                    help="refresh results/ci_port_suite.json from a green main CI run, then exit")
    args = ap.parse_args()
    if args.fetch_ci is not None:
        fetch_ci(args.fetch_ci or None)
        return 0
    if args.check:
        report = stale(args.out)
        if report:
            print("\n".join(report))
            print("run make export-static and commit the result", file=sys.stderr)
        return 1 if report else 0
    files, meta = build()
    write(files, args.out)
    print(f"{len(files)} files in {args.out}: {meta['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
