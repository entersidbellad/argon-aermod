#!/usr/bin/env python3
"""List ``state.X`` / ``state.prime.x`` attribute reads in port modules that the
state classes do not define (a static check used to brief Argon; edits nothing).

    python agent/attr_check.py prime_base.py prime_wake.py ...
"""
from __future__ import annotations

import ast
import dataclasses
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "port"))
import aermod_py.state as st  # noqa: E402

PORT = ROOT / "port" / "aermod_py"


def fields(cls) -> set[str]:
    names = {f.name for f in dataclasses.fields(cls)} | set(dir(cls))
    return names


def check(files: list[str]) -> dict[str, dict[str, list[int]]]:
    main = fields(st.AermodState)
    try:
        import aermod_py.prime_state as ps
        prime = fields(ps.PrimeState)
    except Exception:
        prime = set()
    lower = {n.lower(): n for n in main}
    out: dict[str, dict[str, list[int]]] = {}
    for rel in files:
        tree = ast.parse((Path(rel) if Path(rel).is_absolute() else PORT / rel).read_text())
        assigned_main, assigned_prime = set(), set()
        reads = defaultdict(list)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                v = node.value
                if isinstance(v, ast.Name) and v.id in ("state", "st"):
                    key = ("main", node.attr)
                elif (isinstance(v, ast.Attribute) and v.attr == "prime"
                      and isinstance(v.value, ast.Name) and v.value.id in ("state", "st")):
                    key = ("prime", node.attr)
                elif isinstance(v, ast.Name) and v.id in ("p", "ps", "prm", "pr"):
                    key = ("prime", node.attr)
                else:
                    continue
                reads[key].append(node.lineno)
        bad = {}
        for (kind, name), lines in sorted(reads.items()):
            if kind == "main" and name not in main and name != "prime":
                hint = lower.get(name.lower())
                bad[f"state.{name}" + (f"  (AermodState has {hint})" if hint else
                                       "  (not on AermodState)")] = lines
            if kind == "prime" and prime and name not in prime:
                bad[f"prime.{name}  (not on PrimeState)"] = lines
        out[rel] = bad
    return out


if __name__ == "__main__":
    for rel, bad in check(sys.argv[1:]).items():
        print(f"## {rel}: {len(bad)} unknown attributes")
        for k, lines in bad.items():
            print(f"- `{k}` lines {', '.join(map(str, sorted(set(lines))[:8]))}")
