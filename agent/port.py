#!/usr/bin/env python3
"""One-pass full-context port of AERMOD's physics by Gemini 4 Argon.

    python pack.py                       # context/tier_<T>.txt
    python agent/port.py --tier B        # needs GEMINI_API_KEY
    python agent/port.py --tier B --dry-run   # build and count the prompt only

The system instruction is prompts/port.md; the input is the contract,
harness/glue.py, the SETUP input names, the DEBUGOPT catalogue and the packed
Fortran. The reply is saved to agent/runs/<run>/reply.txt, split into
port/aermod_py/ by split.py (which records provenance in files.json), and the
run is smoke-tested with harness/run_port.py on the tier's first case.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import argon  # noqa: E402
import cases as catalog  # noqa: E402
import pack  # noqa: E402
import run_port  # noqa: E402
import split  # noqa: E402

PROMPTS = ROOT / "prompts"
RUNS = ROOT / "agent" / "runs"
SETUP_INPUTS = ROOT / "harness" / "setup_inputs.json"
FORTRAN_TYPES = {"D": "DOUBLE PRECISION", "I": "INTEGER", "L": "LOGICAL", "C": "CHARACTER"}


def setup_table() -> str:
    rows = ["| name | module | type | rank |", "|---|---|---|---|"]
    for e in json.loads(SETUP_INPUTS.read_text()):
        rows.append(f"| `{e['name']}` | {e['module']} | {FORTRAN_TYPES.get(e['type'], e['type'])} "
                    f"| {e['rank']}{' (allocatable)' if e.get('allocatable') else ''} |")
    return "\n".join(rows)


def shared_parts() -> list[tuple[str, str]]:
    """What every request needs besides Fortran: the contract, glue, SETUP inputs and debug names."""
    return [
        ("Contract (prompts/contract.md)", (PROMPTS / "contract.md").read_text()),
        ("harness/glue.py (import it; do not port it)",
         "```python\n" + (ROOT / "harness" / "glue.py").read_text() + "```"),
        ("SETUP inputs (harness/setup_inputs.json): the keys of `setup`", setup_table()),
        ("DEBUGOPT variables (prompts/debug_vars.md)", (PROMPTS / "debug_vars.md").read_text()),
    ]


def shared_context() -> str:
    return "\n\n".join(f"# {title}\n\n{text}" for title, text in shared_parts())


def build_input(tier: str) -> str:
    fortran = pack.CONTEXT / f"tier_{tier}.txt"
    if not fortran.exists():
        raise SystemExit(f"{fortran} missing; run python pack.py --tier {tier}")
    parts = shared_parts() + [(f"Fortran, tier {tier}", fortran.read_text())]
    body = "\n\n".join(f"# PART {i}: {title}\n\n{text}" for i, (title, text) in enumerate(parts, 1))
    return body + f"\n\n# TASK\n\nWrite the complete `aermod_py` package for tier {tier} now.\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", choices=["A", "B"], default="B")
    ap.add_argument("--thinking", choices=argon.THINKING_LEVELS, default="high")
    ap.add_argument("--max-output-tokens", type=int, default=None)
    ap.add_argument("--agent", action="store_true",
                    help="run through the Antigravity agent (untested against the service)")
    ap.add_argument("--run-id", help="default: port_<tier>_<UTC timestamp>")
    ap.add_argument("--dry-run", action="store_true", help="write the prompt and count tokens only")
    args = ap.parse_args()

    run_id = args.run_id or f"port_{args.tier}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    system = (PROMPTS / "port.md").read_text()
    prompt = build_input(args.tier)
    (run_dir / "prompt.txt").write_text(system + "\n\n" + prompt)
    counter = pack.TokenCounter()
    tokens = counter(system + prompt)
    meta = {"run_id": run_id, "kind": "port", "tier": args.tier, "model": argon.MODEL, "thinking": args.thinking,
            "agent": args.agent, "prompt_tokens": tokens, "token_method": counter.method}
    (run_dir / "run.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"{run_id}: prompt {tokens:,} tokens ({counter.method})")
    if args.dry_run:
        return 0

    try:
        reply = argon.ask(argon.make_client(), input=prompt, system_instruction=system,
                          thinking_level=args.thinking, max_output_tokens=args.max_output_tokens,
                          agent=args.agent)
    except argon.ArgonError as exc:
        if exc.reply is not None:
            exc.reply.save(run_dir)
        print(f"{run_id}: {exc}", file=sys.stderr)
        return 1
    reply.save(run_dir)
    print(f"{run_id}: {reply.status} in {reply.seconds:.0f}s, usage {reply.usage}")

    files = split.parse(reply.text)
    split.clear()
    written = split.write(files)
    split.record(written, run_dir / "reply.txt", interaction_id=reply.id, step="port")
    print(f"{run_id}: wrote {len(written)} files to {split.PORT_DIR.relative_to(ROOT)}")

    smoke = run_port.run_case(catalog.tier_cases(args.tier)[0], who="port")
    print(f"{run_id}: smoke test {smoke.case} {'ok' if smoke.ok else 'FAILED'}")
    if not smoke.ok:
        print(smoke.error, file=sys.stderr)
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
