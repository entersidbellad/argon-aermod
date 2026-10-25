#!/usr/bin/env python3
"""Baseline: the same port in requests of at most 128K input tokens.

    python agent/baselines/chunked.py --tier B            # needs GEMINI_API_KEY
    python agent/baselines/chunked.py --tier B --dry-run  # plan and count only

Same model, contract and harness as agent/port.py, but no request sees the
whole Fortran. Every request carries the contract, harness/glue.py, the SETUP
input names and the DEBUGOPT catalogue. The first request ports modules.f into
state.py; each later one adds an interface summary of the Python written so
far (module-level names, dataclass fields, function signatures and docstrings)
and as many program units as fit, callees before callers, so HRLOOP comes last.
Output goes to agent/baselines/chunked_tier_<T>/aermod_py (gitignored), never
to port/.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "harness"), str(ROOT / "agent")]
import argon  # noqa: E402
import cases as catalog  # noqa: E402
import pack  # noqa: E402
import port  # noqa: E402
import run_port  # noqa: E402
import split  # noqa: E402

CAP = 128_000
PROMPTS = ROOT / "prompts"
# Callees before callers; modules.f is the first request on its own.
FILE_ORDER = ["prime.f", "sigmas.f", "prise.f", "windgrid.f", "tempgrid.f", "siggrid.f",
              "iblval.f", "metext.f", "calc2.f", "calc1.f", "aermod.f"]


def fixed_parts() -> str:
    return "\n\n".join([
        "# Contract (prompts/contract.md)\n\n" + (PROMPTS / "contract.md").read_text(),
        "# harness/glue.py (import it; do not port it)\n\n```python\n"
        + (ROOT / "harness" / "glue.py").read_text() + "```",
        "# SETUP inputs: the keys of `setup`\n\n" + port.setup_table(),
        "# DEBUGOPT variables\n\n" + (PROMPTS / "debug_vars.md").read_text(),
    ])


def interface(pkg: Path) -> str:
    """Module-level names, class fields and function signatures+docstrings of the package."""
    out = []
    for path in sorted(pkg.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as exc:
            out.append(f"## aermod_py/{path.relative_to(pkg)} (does not parse: {exc})")
            continue
        out.append(f"## aermod_py/{path.relative_to(pkg)}")
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                head = ast.unparse(node).split("\n")[0]
                doc = ast.get_docstring(node)
                out.append(head + (f'\n    """{doc.splitlines()[0]}"""' if doc else ""))
                if isinstance(node, ast.ClassDef):
                    out += [f"    {ast.unparse(s)}" for s in node.body if isinstance(s, ast.AnnAssign)]
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                out.append(ast.unparse(node)[:200])
    return "\n".join(out)


def chunks(tier: str, budget: int, counter: pack.TokenCounter) -> list[list[pack.Unit]]:
    units, _ = pack.select_units(tier)
    cache: dict[str, list[str]] = {}
    by_file: dict[str, list[pack.Unit]] = {}
    for u in units:
        by_file.setdefault(u.file, []).append(u)
    plan = [by_file.pop("modules.f")]
    for f in FILE_ORDER + sorted(by_file):
        current, size = [], 0
        for u in reversed(by_file.pop(f, [])):        # within a file, later units are often callees
            n = counter(pack.unit_text(u, cache))
            if current and size + n > budget:
                plan.append(current)
                current, size = [], 0
            current.append(u)
            size += n
        if current:
            plan.append(current)
    return plan


def module_name(units: list[pack.Unit], step: int) -> str:
    return f"{Path(units[0].file).stem}_{step:02d}.py"


def chunk_input(units: list[pack.Unit], fixed: str, summary: str, step: int, total: int) -> str:
    cache: dict[str, list[str]] = {}
    src = "\n".join(f"##### UNIT {u.name} ({u.kind}) {u.file}:{u.start}-{u.end}\n"
                    + pack.unit_text(u, cache) for u in units)
    names = ", ".join(u.name for u in units)
    task = (f"Request {step} of {total}. Translate these Fortran units: {names}. "
            + ("This is MODULE state: write aermod_py/state.py with one dataclass per MODULE "
               "(fields named as in the Fortran) and aermod_py/constants.py for PARAMETERs."
               if step == 1 else
               f"Write them to aermod_py/{module_name(units, step)}. Call the Python already "
               "written (interface above) rather than redefining it. "
               + ("HRLOOP is here: also write aermod_py/__init__.py exporting run_case."
                  if any(u.name == "HRLOOP" for u in units) else "")))
    return (f"{fixed}\n\n# Python written so far\n\n{summary or '(none)'}\n\n"
            f"# Fortran\n\n{src}\n\n# TASK\n\n{task}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", choices=["A", "B"], default="B")
    ap.add_argument("--thinking", choices=argon.THINKING_LEVELS, default="high")
    ap.add_argument("--summary-reserve", type=int, default=20_000,
                    help="tokens kept free for the interface summary")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out_root = ROOT / "agent" / "baselines" / f"chunked_tier_{args.tier}"
    pkg = out_root / "aermod_py"
    run_dir = out_root / f"run_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    counter = pack.TokenCounter()
    system = (PROMPTS / "chunked_port.md").read_text()
    fixed = fixed_parts()
    budget = CAP - counter(system) - counter(fixed) - args.summary_reserve - 1_000
    plan = chunks(args.tier, budget, counter)
    print(f"tier {args.tier}: {len(plan)} requests, Fortran budget {budget:,} tokens each "
          f"({counter.method})")
    for i, units in enumerate(plan, 1):
        print(f"  {i:2d}: {units[0].file:12s} {len(units):3d} units  {units[0].name} .. {units[-1].name}")
    if args.dry_run:
        return 0

    client = argon.make_client()
    run_dir.mkdir(parents=True)
    split.clear(pkg) if pkg.exists() else pkg.mkdir(parents=True)
    log = []
    for i, units in enumerate(plan, 1):
        prompt = chunk_input(units, fixed, interface(pkg), i, len(plan))
        tokens = counter(system + prompt)
        if tokens > CAP:
            raise SystemExit(f"request {i} is {tokens:,} tokens; raise --summary-reserve")
        step_dir = run_dir / f"step_{i:02d}"
        step_dir.mkdir()
        (step_dir / "prompt.txt").write_text(system + "\n\n" + prompt)
        reply = argon.ask(client, input=prompt, system_instruction=system,
                          thinking_level=args.thinking)
        reply.save(step_dir)
        files = split.parse(reply.text)
        clobbered = [str(rel) for rel, _ in files if (pkg / rel).exists()]
        if clobbered:
            raise SystemExit(f"step {i} rewrote existing files {clobbered}; see {step_dir}")
        written = split.write(files, pkg)
        split.record(written, step_dir / "reply.txt", pkg, interaction_id=reply.id, step=i)
        log.append({"step": i, "units": [u.name for u in units], "prompt_tokens": tokens,
                    "usage": reply.usage, "files": [str(p.relative_to(pkg)) for p in written]})
        print(f"step {i}: {len(written)} files, usage {reply.usage}")
    (run_dir / "steps.json").write_text(json.dumps(log, indent=1) + "\n")
    smoke = run_port.run_case(catalog.tier_cases(args.tier)[0], who=f"chunked_{args.tier}",
                              package_dir=pkg)
    print(f"smoke test {smoke.case}: {'ok' if smoke.ok else 'FAILED'}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
