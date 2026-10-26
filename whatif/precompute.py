#!/usr/bin/env python3
"""Run every stack in whatif/kiln.toml's grid through the Argon-ported AERMOD at 1 g/s.

  python whatif/precompute.py [--workers 4] [--only KEY ...] [--force]

Writes whatif/cache/<stack key>.json (unit-rate statistics, receptors, the
port's sha256 and the run time) and skips stacks already cached with the
current port unless --force. Needs the met files from ref/fetch.py. Each stack
is a full year of met on the configured receptor grid, so expect one to two
minutes per stack per worker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenario  # noqa: E402

WORK_DIR = scenario.catalog.OUT_DIR / "whatif"


def _one(stack: scenario.Stack) -> tuple[str, float, str]:
    config = scenario.load_config()
    try:
        field = scenario.run(stack, config, WORK_DIR / stack.key)
    except Exception as exc:
        return stack.key, 0.0, f"{type(exc).__name__}: {exc}"
    record = scenario.cache_record(field, config)
    tmp = scenario.CACHE_DIR / f".{stack.key}.json.tmp"
    tmp.write_text(json.dumps(record, separators=(",", ":")) + "\n")
    os.replace(tmp, scenario.CACHE_DIR / f"{stack.key}.json")
    return stack.key, field.seconds, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--only", nargs="*", help="stack keys, e.g. H80_D4_T423_V16")
    ap.add_argument("--force", action="store_true", help="recompute stacks already cached")
    args = ap.parse_args()

    config = scenario.load_config()
    port = scenario.run_port.package_sha256(scenario.run_port.PORT_DIR)
    scenario.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    todo = []
    for stack in scenario.grid(config):
        if args.only and stack.key not in args.only:
            continue
        cached = scenario.load_cached(stack)
        if cached and cached["port_sha256"] == port and not args.force:
            continue
        todo.append(stack)
    print(f"{len(todo)} stacks to run with {args.workers} workers (port {port[:12]})", flush=True)
    t0, failed = time.monotonic(), 0
    with Pool(args.workers) as pool:
        for i, (key, seconds, error) in enumerate(pool.imap_unordered(_one, todo), 1):
            failed += bool(error)
            print(f"[{i}/{len(todo)}] {key:22s} " + (f"FAIL {error}" if error else f"{seconds:6.1f}s"),
                  flush=True)
    print(f"done in {time.monotonic() - t0:.0f}s, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
