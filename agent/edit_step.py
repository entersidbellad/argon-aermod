#!/usr/bin/env python3
"""One recorded Argon edit of the port: a refactor or a chunked port step.

    python agent/edit_step.py --run-id import_fix --task prompts/tasks/import_fix.md \
        --show hrloop.py metext.py __init__.py --budget-usd 4

The request is a task file (system instruction prompts/edit.md), optional shared
context (contract, glue, SETUP inputs, debug names), optional Fortran units from
the comment-stripped pack, and the current text of the port files named with
``--show``. Argon returns complete files in ``=== FILE: ===`` form. They are
written to port/aermod_py and kept only if every acceptance check passes:

- no tier A training or holdout case that passed before fails afterwards;
- ``--import-check``: each listed module imports in a fresh interpreter, in
  every given order;
- the reply touches at most ``--max-files`` files.

Otherwise the previous files are restored. Kept files are recorded in files.json
beside the reply (split.record), so ``split.py --verify`` traces them to this
interaction. Spend is priced from the reply's usage; the request is refused when
its input alone would pass ``--budget-usd`` given ``--spent-usd`` already spent.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import argon  # noqa: E402
import cases as catalog  # noqa: E402
import pack  # noqa: E402
import port  # noqa: E402
import repair_loop as rl  # noqa: E402
import split  # noqa: E402

RUNS = ROOT / "agent" / "runs"
PROMPTS = ROOT / "prompts"
DEFAULT_PRICES = argon.Prices(2.0, 10.0)   # gemini-4-argon introductory, through 2026-11-30


def import_ok(order: list[str]) -> tuple[bool, str]:
    code = "import " + ", ".join(f"port.aermod_py.{m}" for m in order)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "harness"), PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    return p.returncode == 0, (p.stderr.strip().splitlines() or [""])[-1]


def api_index(port_dir: Path) -> str:
    """Every function and class in the port: signature and first docstring line."""
    out = []
    for rel, text in rl.python_files(port_dir).items():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        rows = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                doc = (ast.get_docstring(node) or "").strip().splitlines()
                head = (f"def {node.name}({ast.unparse(node.args)})"
                        + (f" -> {ast.unparse(node.returns)}" if getattr(node, "returns", None) else "")
                        if isinstance(node, ast.FunctionDef) else f"class {node.name}")
                rows.append(f"  {head}" + (f"   # {doc[0]}" if doc else ""))
        if rows:
            out.append(f"aermod_py/{rel}:\n" + "\n".join(rows))
    return "\n".join(out)


def unit_source(name: str, tier: str, strip: bool) -> str:
    rec = pack.load_index(tier)[name.upper()]
    text = pack.fortran_unit(name, tier)
    if strip:
        text = "\n".join(ln for ln in text.split("\n") if ln.strip() and not pack.is_comment(ln))
    return f"##### UNIT {name} {rec['file']}:{rec['start']}-{rec['end']}\n```fortran\n{text}\n```"


def range_source(spec: str, strip: bool) -> str:
    fname, span = spec.split(":")
    a, b = (int(x) for x in span.split("-"))
    lines = (pack.SRC / fname).read_text(encoding="latin-1").split("\n")[a - 1:b]
    if strip:
        lines = [ln for ln in lines if ln.strip() and not pack.is_comment(ln)]
    return f"##### {fname}:{a}-{b}\n```fortran\n" + "\n".join(lines) + "\n```"


def build_input(task: str, show: list[str], units: list[str], tier: str, shared: bool,
                port_dir: Path, strip: bool = False, ranges: list[str] = (),
                with_api: bool = False, notes: list[Path] = ()) -> str:
    parts = []
    if shared:
        parts.append(port.shared_context())
    for n in notes:
        parts.append(n.read_text())
    if with_api:
        parts.append("# Current port API (every module's functions)\n\n```\n"
                     + api_index(port_dir) + "\n```")
    for spec in ranges:
        parts.append(f"# Fortran\n\n{range_source(spec, strip)}")
    for u in units:
        try:
            parts.append(f"# Fortran\n\n{unit_source(u, tier, strip)}")
        except KeyError:
            raise SystemExit(f"Fortran unit {u} not in tier {tier} index")
    files = rl.python_files(port_dir)
    for rel in show:
        if rel in files:
            parts.append(f"# Current Python: aermod_py/{rel}\n\n```python\n{files[rel]}```")
    parts.append("# TASK\n\n" + task)
    return "\n\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--task", type=Path, required=True)
    ap.add_argument("--system", type=Path, default=PROMPTS / "edit.md")
    ap.add_argument("--show", nargs="*", default=[], help="port files to include")
    ap.add_argument("--units", nargs="*", default=[], help="Fortran units to include")
    ap.add_argument("--fortran-range", action="append", default=[],
                    help="FILE:START-END lines of the EPA source to include (e.g. modules.f:4065-4331)")
    ap.add_argument("--strip", action="store_true", help="drop Fortran comment lines")
    ap.add_argument("--api", action="store_true", help="include the port's function index")
    ap.add_argument("--notes", type=Path, action="append", default=[],
                    help="extra markdown included before the Fortran (e.g. a design plan)")
    ap.add_argument("--tier", default="B")
    ap.add_argument("--shared", action="store_true", help="include contract/glue/setup/debug names")
    ap.add_argument("--max-files", type=int, default=6)
    ap.add_argument("--import-check", nargs="*", default=[],
                    help="orders like 'metext,hrloop' that must import in a fresh interpreter")
    ap.add_argument("--thinking", default="high")
    ap.add_argument("--max-output-tokens", type=int, default=65_536)
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--spent-usd", type=float, default=0.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-tier-a-check", action="store_true")
    ap.add_argument("--resume-id", help="fetch this already-created interaction instead of "
                    "sending the prompt again (pending.json records it)")
    args = ap.parse_args()

    port_dir = split.PORT_DIR
    run_dir = RUNS / args.run_id
    pending = run_dir / "pending.json"
    if not args.resume_id and pending.exists():
        args.resume_id = json.loads(pending.read_text())["interaction_id"]
        print(f"resuming interaction {args.resume_id} from {pending}")
    if (run_dir / "reply.txt").exists():
        raise SystemExit(f"{run_dir} already has a reply; use a new --run-id")
    run_dir.mkdir(parents=True, exist_ok=True)
    system = args.system.read_text()
    prompt = build_input(args.task.read_text(), args.show, args.units, args.tier, args.shared,
                         port_dir, args.strip, args.fortran_range, args.api, args.notes)
    (run_dir / "prompt.txt").write_text(system + "\n\n" + prompt)
    client = argon.make_client()
    n = int(client.models.count_tokens(model=argon.MODEL,
                                       contents=system + "\n\n" + prompt).total_tokens)
    prices = argon.Prices.from_args(None, None) or DEFAULT_PRICES
    floor = prices.cost({"total_input_tokens": n})
    worst = floor + prices.cost({"total_output_tokens": args.max_output_tokens})
    meta = {"run_id": args.run_id, "kind": "edit", "model": argon.MODEL, "thinking": args.thinking,
            "task": str(args.task.resolve().relative_to(ROOT)), "shown": args.show, "units": args.units,
            "fortran_ranges": args.fortran_range, "strip_comments": args.strip,
            "notes": [str(n.resolve().relative_to(ROOT)) for n in args.notes],
            "prompt_tokens": n, "token_method": "Gemini count_tokens (gemini-4-argon)",
            "max_output_tokens": args.max_output_tokens, "budget_usd": args.budget_usd,
            "spent_before_usd": args.spent_usd, "prices_usd_per_mtok": asdict(prices),
            "started": datetime.now(timezone.utc).isoformat()}
    (run_dir / "run.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"{args.run_id}: prompt {n:,} tokens; input ${floor:.3f}, worst case ${worst:.3f}",
          flush=True)
    if args.dry_run:
        return 0
    if args.spent_usd + worst > args.budget_usd and not args.resume_id:
        print(f"BUDGET: ${args.spent_usd:.2f} spent + worst ${worst:.2f} > ${args.budget_usd:.2f}")
        return 3

    tier_a = catalog.tier_cases("A") + [c for c in catalog.CASES if c.tier == "holdout"
                                        and c.name == "testpm10_stack2"]
    before_scores = None if args.no_tier_a_check else rl.score(tier_a, port_dir, "port_edit")

    try:
        reply = argon.ask(client, input=prompt, system_instruction=system,
                          thinking_level=args.thinking, max_output_tokens=args.max_output_tokens,
                          resume_id=args.resume_id,
                          on_created=lambda i: pending.write_text(json.dumps({"interaction_id": i}) + "\n"))
    except argon.ArgonError as exc:
        cost = 0.0
        if exc.reply is not None:
            exc.reply.save(run_dir)
            cost = prices.cost(exc.reply.usage)
        (run_dir / "decision.json").write_text(json.dumps(
            {"accepted": False, "reason": f"model error: {exc}", "cost_usd": cost}, indent=1) + "\n")
        print(f"model error: {exc} (${cost:.3f})")
        return 1
    reply.save(run_dir)
    cost = prices.cost(reply.usage)
    u = reply.usage
    print(f"{reply.id}: in={u.get('total_input_tokens')} out={u.get('total_output_tokens')} "
          f"thought={u.get('total_thought_tokens')} cached={u.get('total_cached_tokens')} "
          f"cost=${cost:.3f} ({reply.seconds:.0f}s)", flush=True)
    decision = {"interaction_id": reply.id, "usage": u, "cost_usd": cost,
                "hypothesis": rl.hypothesis(reply.text), "accepted": False, "reason": ""}
    try:
        files = split.parse(reply.text)
        if len(files) > args.max_files:
            raise split.SplitError(f"{len(files)} files, at most {args.max_files} allowed")
    except split.SplitError as exc:
        decision["reason"] = f"unusable reply: {exc}"
    else:
        snap = rl.snapshot(port_dir)
        try:
            written = split.write(files, port_dir)
            decision["files"] = [str(p.relative_to(port_dir)) for p in written]
            problems = []
            for order in args.import_check:
                ok, err = import_ok(order.split(","))
                if not ok:
                    problems.append(f"import {order}: {err}")
            if before_scores is not None and not problems:
                after = rl.score(tier_a, port_dir, "port_edit")
                decision["tier_a"] = {k: v.summary or v.error[-300:] for k, v in after.items()}
                broke = rl.regressions(before_scores, after)
                if broke:
                    problems.append("broke " + ", ".join(broke))
            if problems:
                decision["reason"] = "; ".join(problems)
            else:
                decision["accepted"], decision["reason"] = True, "all checks pass"
        except Exception as exc:
            decision["reason"] = f"evaluation failed: {type(exc).__name__}: {exc}"
        except BaseException:
            rl.restore(port_dir, snap)
            raise
        if decision["accepted"]:
            split.record(written, run_dir / "reply.txt", port_dir, interaction_id=reply.id,
                         step="edit", run=args.run_id)
        else:
            rl.restore(port_dir, snap)
    (run_dir / "decision.json").write_text(json.dumps(decision, indent=1, default=str) + "\n")
    (run_dir / "result.json").write_text(json.dumps(
        {"accepted": decision["accepted"], "reason": decision["reason"], "spent_usd": cost,
         "interaction_id": reply.id}, indent=1) + "\n")
    print(f"{'KEPT' if decision['accepted'] else 'REVERTED'}: {decision['reason']}")
    return 0 if decision["accepted"] else 2


if __name__ == "__main__":
    sys.exit(main())
