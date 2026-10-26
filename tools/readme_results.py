#!/usr/bin/env python3
"""Regenerate the results block of README.md from committed files.

  python tools/readme_results.py           # rewrite the block in README.md
  python tools/readme_results.py --check   # exit 1 if the block is stale

Every number in the block comes from server.summary(use_suite=False), i.e. from
results/tier_*.md, agent/runs/*, context/tokens.json and port/aermod_py, never
from this machine's out/. When Tier B results land in results/, rerun this.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server  # noqa: E402

README = ROOT / "README.md"
BEGIN = "<!-- results:begin -->"
END = "<!-- results:end -->"
SCOPE = {"A": "POINT sources, flat rural terrain, 1-hour, no building downwash",
         "B": "Tier A plus PRIME building downwash"}
STATUS = {"passing": "**all pass**", "failing": "**failing**",
          "not_scored": "not scored", "in_progress": "in progress (not yet published)"}


def _n(x) -> str:
    return "-" if x is None else f"{x:,}"


def _usd(x) -> str:
    return "-" if x is None else f"${x:,.2f}"


def _count(t: dict) -> str:
    if not t["cases"]:
        return "none"
    return f"{t['passing']}/{len(t['cases'])}" if t["scored"] else "not yet scored"


def _sci(x) -> str:
    return "-" if x is None else f"{x:.2e}"


def render(summary: dict, scores: dict) -> str:
    lines = ["| Tier | Scope | Training cases passing | Holdout passing | Status |",
             "|---|---|---|---|---|"]
    for tier, t in summary["tiers"].items():
        lines.append(f"| {tier} | {SCOPE[tier]} | {_count(t['training'])} | "
                     f"{_count(t['holdout'])} | {STATUS[t['status']]} |")
    s = summary["scores"]
    lines += ["", f"Scores from `{s['source']}`" + (f", scored {s['suite_time']}" if s["suite_time"] else "")
              + (", with the approved `harness/compare.py`." if s["hash_matches"] and summary["compare_frozen"]
                 else ", **not** with the approved `harness/compare.py`."), ""]

    rows = [(name, info, scores["results"][name]) for name, info in scores["cases"].items()
            if name in scores["results"]]
    if rows:
        lines += ["| Case | Tests tier | Role | Result | Best-fit slopes (origin / OLS / mean ratio) "
                  "| Zero/nonzero agreement | p99 relative error | H4H receptors failing |",
                  "|---|---|---|---|---|---|---|---|"]
        for name, info, r in rows:
            slopes = "/".join("-" if v is None else f"{v:.6f}"
                              for v in (r.get("slope"), r.get("slope_ols"), r.get("mean_ratio")))
            zero = "-" if r.get("zero_agreement") is None else f"{100 * r['zero_agreement']:.3f}%"
            lines.append(f"| `{name}` | {info['tests_tier']} | "
                         f"{'holdout' if info['tier'] == 'holdout' else 'training'} | "
                         f"{'PASS' if r['passes'] else 'FAIL'} | {slopes} | {zero} | "
                         f"{_sci(r.get('p99_rel_err'))} | {r.get('h4h_fails') or '-'} |")
        lines.append("")

    a = summary["argon"]
    lines += ["| Argon run | Kind | Tier | Model (thinking) | Interactions | Billed input tokens "
              "| Output + thinking tokens | Cost |", "|---|---|---|---|---|---|---|---|"]
    for r in a["runs"]:
        model = f"{r['model']} ({r['thinking']})" if r["model"] else "not recorded"
        lines.append(f"| `{r['id']}` | {r['kind'] or '-'} | {r['tier'] or '-'} | {model} | "
                     f"{r['replies']} | {_n(r['usage']['total_input_tokens'])} | "
                     f"{_n(r['usage']['total_output_tokens'] + r['usage']['total_thought_tokens'])} | "
                     f"{_usd(r['cost_usd'])} |")
    u = a["usage"]
    lines.append(f"| **Total** | | | | {a['interactions']} | {_n(u['total_input_tokens'])} | "
                 f"{_n(u['total_output_tokens'] + u['total_thought_tokens'])} | "
                 f"**{_usd(a['cost_usd'])}**{'' if a['cost_complete'] else ' (partial)'} |")
    lines += [""] + [f"Costs from `{p['path']}`: {p['prices']}" for p in a["prices"]]

    p = summary["provenance"]
    lines += ["", f"Provenance: {p['python_files']} Python files in `port/aermod_py`, "
              + (f"every one traced to {p['interactions']} recorded Argon interaction(s) by "
                 "`split.py --verify`." if p["ok"] else "**some files are not traceable**.")]

    tok = summary["tokens"]
    if tok:
        lines += ["", "| Fortran in scope (tiktoken o200k proxy) | Program units | Lines | "
                  "Tokens, code only (sent by default) | Tokens with comments |", "|---|---|---|---|---|"]
        for tier in sorted(tok):
            t = tok[tier]
            lines.append(f"| Tier {tier} | {_n(t.get('units'))} | {_n(t.get('lines'))} | "
                         f"{_n(t.get('tokens_code_only'))} | {_n(t.get('tokens_with_comments'))} |")
    return "\n".join(lines)


def block() -> str:
    body = render(server.summary(use_suite=False), server._scores("port", use_suite=False))
    return (f"{BEGIN}\n<!-- generated by `make readme` from results/, agent/runs/, context/ and "
            f"port/; edit tools/readme_results.py, not this block -->\n\n{body}\n\n{END}")


def replace(text: str, new_block: str) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"README.md has no {BEGIN} ... {END} block")
    return pattern.sub(lambda _: new_block, text, count=1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if README.md's block is stale")
    args = ap.parse_args()
    text = README.read_text()
    new = replace(text, block())
    if args.check:
        if new != text:
            print("README.md results block is stale: run make readme", file=sys.stderr)
            return 1
        print("README.md results block is up to date")
        return 0
    README.write_text(new)
    print("README.md results block regenerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
