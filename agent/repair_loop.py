#!/usr/bin/env python3
"""Repair loop: find the port's first divergence from AERMOD and ask Argon to fix it.

    python agent/repair_loop.py --tier B --iterations 50     # needs GEMINI_API_KEY

Each iteration:

1. Run the port on every training case of the tier (harness/run_port.py) and
   judge each with harness/compare.py. Stop when all pass.
2. Take the first failing case. If the port crashed, the problem is the
   traceback. Otherwise rerun it with debug rows and diff them against
   out/ref_debug/<case> (harness/debugdiff.py); the problem is the first
   divergent or missing record in AERMOD's order.
3. Send prompts/repair.md with the problem, that hour's met, the Fortran unit
   that printed the value (pack.fortran_unit) and the Python files that
   translate it. After three rejected attempts on the same variable, send
   prompts/consult.md with the full packed Fortran and the whole port instead.
4. Apply the reply's files (at most two for a repair). Keep the patch only if no
   training case that passed now fails and the target case improved: it
   passes, it no longer crashes, or its first problem moved later in AERMOD's
   order. Otherwise restore the previous files.

The holdout case is never used for repair; it is scored once at the end.
Accepted patches are recorded in files.json beside their reply, so
``split.py --verify`` can trace every port file to model output.
"""

from __future__ import annotations

import argparse
import ast
import json
import pickle
import re
import sys
import warnings
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import argon  # noqa: E402
import cases as catalog  # noqa: E402
import compare  # noqa: E402
import dbgparse  # noqa: E402
import debugdiff  # noqa: E402
import glue  # noqa: E402
import pack  # noqa: E402
import port  # noqa: E402
import run_port  # noqa: E402
import run_ref  # noqa: E402
import split  # noqa: E402

PROMPTS = ROOT / "prompts"
RUNS = ROOT / "agent" / "runs"
MAX_REPAIR_FILES = 2
CONSULT_AFTER = 3
MET_SHOWN = ["OBULEN", "USTAR", "WSTAR", "ZICONV", "ZIMECH", "VPTGZI", "SFCHF", "UREF",
             "UREFHT", "WDREF", "TA", "SFCZ0", "BOWEN", "ALBEDO"]
UNIT_IN_DOC = re.compile(r"\b(?:SUBROUTINE|FUNCTION|MODULE)\s+([A-Z][A-Z0-9_]*)")


@dataclass
class CaseScore:
    case: str
    ran: bool
    passes: bool
    error: str = ""
    summary: str = ""


@dataclass
class Problem:
    case: str
    kind: str                         # "crash", "divergence", "missing", "postfile"
    text: str                         # what the model is told
    sub: str = ""                     # Fortran unit to show
    var: str = ""
    date: int = 0
    rank: tuple = ()                  # larger is later in AERMOD's order (progress)

    @property
    def target(self) -> str:
        return f"{self.sub}.{self.var}" if self.var else f"{self.kind}:{self.sub}"


@dataclass
class Attempt:
    iteration: int
    mode: str
    problem: str
    hypothesis: str
    accepted: bool
    reason: str
    interaction_id: str = ""
    usage: dict = field(default_factory=dict)


# --- scoring -----------------------------------------------------------------

def score(cases: list[catalog.Case], port_dir: Path, who: str) -> dict[str, CaseScore]:
    out = {}
    for case in cases:
        run = run_port.run_case(case, who=who, package_dir=port_dir)
        if not run.ok:
            out[case.name] = CaseScore(case.name, False, False, run.error)
            continue
        paths = compare._case_paths(case.name, who)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = compare.compare_case(**paths)
        out[case.name] = CaseScore(case.name, True, res.passes, summary=compare.format_row(res))
    return out


def regressions(before: dict[str, CaseScore], after: dict[str, CaseScore]) -> list[str]:
    return [n for n, s in before.items() if s.passes and not after[n].passes]


# --- diagnosis ---------------------------------------------------------------

def python_files(port_dir: Path) -> dict[str, str]:
    return {str(p.relative_to(port_dir)): p.read_text()
            for p in sorted(port_dir.rglob("*.py")) if "__pycache__" not in p.parts}


def units_in(source: str, function: str) -> list[str]:
    """Fortran units named in the docstring of ``function`` in a Python source file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return UNIT_IN_DOC.findall(ast.get_docstring(node) or "")
    return []


def files_translating(port_dir: Path, sub: str) -> list[str]:
    pattern = re.compile(rf"\b(?:SUBROUTINE|FUNCTION)\s+{re.escape(sub)}\b")
    return [rel for rel, text in python_files(port_dir).items() if pattern.search(text)]


def crash_problem(case: catalog.Case, error: str, port_dir: Path) -> Problem:
    sub = ""
    port_frames = re.findall(r'File "([^"]+)", line (\d+), in (\w+)', error)
    for path, _, func in reversed(port_frames):
        p = Path(path)
        if p.is_relative_to(port_dir.resolve()):
            names = units_in(p.read_text(), func)
            if names:
                sub = names[0]
                break
    tail = "\n".join(error.strip().splitlines()[-40:])
    return Problem(case.name, "crash", f"The port raised an exception on {case.name}:\n\n{tail}",
                   sub=sub, rank=(-1,))


def met_for(case: catalog.Case, who: str, date: int) -> str:
    workdir = case.out_dir(who)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        project = glue.load_project(workdir / "case.inp")
        met = glue.load_met(project, workdir)
    s = met.surface
    yy = s["IYEAR"] % 100
    kur = yy * 1000000 + s["IMONTH"] * 10000 + s["IDAY"] * 100 + s["IHOUR"]
    hits = np.flatnonzero(kur == date)
    if not len(hits):
        return ""
    h = int(hits[0])
    vals = ", ".join(f"{n}={s[n][h]:g}" for n in MET_SHOWN)
    lo, hi = met.profile_start[h], met.profile_start[h + 1]
    levels = "; ".join(
        f"PFLHT={met.profile['PFLHT'][j]:g} PFLWD={met.profile['PFLWD'][j]:g} "
        f"PFLWS={met.profile['PFLWS'][j]:g} PFLTA={met.profile['PFLTA'][j]:g}"
        for j in range(lo, hi))
    return f"surface record {h} (KURDAT {date}): {vals}\nprofile levels: {levels}"


class Diagnoser:
    """Debug-diffs the port on a case; reference records are parsed once per case."""

    def __init__(self, port_dir: Path, who: str) -> None:
        self.port_dir = port_dir
        self.who = who
        self._ref: dict[str, list[dbgparse.Record]] = {}

    def reference(self, case: catalog.Case) -> list[dbgparse.Record]:
        if case.name not in self._ref:
            workdir = case.out_dir("ref_debug")
            if not any(workdir.glob("*.DBG")):
                run = run_ref.run_case(case, debug=True)
                if not run.ok:
                    raise RuntimeError(f"reference debug run failed for {case.name}")
            self._ref[case.name] = dbgparse.parse_dir(workdir)
        return self._ref[case.name]

    def diagnose(self, case: catalog.Case, current: CaseScore) -> tuple[Problem, debugdiff.Report | None]:
        if not current.ran:
            return crash_problem(case, current.error, self.port_dir), None
        debug_who = self.who + "_debug"
        run = run_port.run_case(case, debug=True, who=debug_who, package_dir=self.port_dir)
        if not run.ok:
            return crash_problem(case, run.error, self.port_dir), None
        with open(case.out_dir(debug_who) / run_port.DEBUG_FILE, "rb") as f:
            rows = pickle.load(f)
        try:
            records = debugdiff.port_records(rows)
        except (ValueError, TypeError) as exc:
            return Problem(case.name, "crash", f"run_case(debug=True) on {case.name} returned "
                           f"malformed debug rows: {exc}", sub="", rank=(-1,)), None
        report = debugdiff.diff(self.reference(case), records, case.name)
        point = report.first_problem
        if point is None:
            return Problem(case.name, "postfile",
                           "Every debug value matches AERMOD, but the POSTFILE does not:\n"
                           + current.summary + "\n" + report.text(), sub="HRLOOP",
                           rank=(len(self.reference(case)), report.n_matched)), report
        date, isrc, irec, comp, sub, var, k = point.key
        kind = "missing" if point.port is None else "divergence"
        text = report.text()
        met = met_for(case, debug_who, date)
        if met:
            text += "\n\nMet for this hour:\n" + met
        return Problem(case.name, kind, text, sub=sub, var=var, date=date,
                       rank=(point.seq, report.n_matched)), report


# --- prompts -----------------------------------------------------------------

def fortran_source(sub: str, tier: str) -> str:
    try:
        rec = pack.load_index(tier)[sub.upper()]
    except KeyError:
        return ""
    return (f"##### UNIT {sub} {rec['file']}:{rec['start']}-{rec['end']}\n"
            f"```fortran\n{pack.fortran_unit(sub, tier)}\n```")


def repair_input(problem: Problem, port_dir: Path, tier: str) -> str:
    parts = [port.shared_context(), f"# Case {problem.case}: {problem.kind}\n\n{problem.text}"]
    if problem.sub:
        src = fortran_source(problem.sub, tier)
        if src:
            parts.append(f"# Fortran\n\n{src}")
    files = python_files(port_dir)
    shown = files_translating(port_dir, problem.sub) if problem.sub else []
    if not shown:
        shown = ["__init__.py"] if "__init__.py" in files else list(files)[:1]
    for rel in shown:
        parts.append(f"# Current Python: aermod_py/{rel}\n\n```python\n{files[rel]}```")
    return "\n\n".join(parts) + "\n"


def consult_input(problem: Problem, history: list[Attempt], port_dir: Path, tier: str) -> str:
    hist = "\n".join(f"- iteration {a.iteration}: {a.hypothesis or '(no hypothesis)'} "
                     f"-> rejected: {a.reason}" for a in history)
    parts = [port.shared_context(), f"# Attempt history for {problem.target}\n\n{hist}",
             f"# Current problem on {problem.case}\n\n{problem.text}"]
    for rel, text in python_files(port_dir).items():
        parts.append(f"# Current Python: aermod_py/{rel}\n\n```python\n{text}```")
    parts.append(f"# Fortran, tier {tier}\n\n" + (pack.CONTEXT / f"tier_{tier}.txt").read_text())
    return "\n\n".join(parts) + "\n"


def hypothesis(text: str) -> str:
    m = re.search(r"===\s*(?:HYPOTHESIS|ANALYSIS)\s*===\s*\n(.*?)(?=^===\s*FILE:|\Z)",
                  text, re.S | re.M)
    return m.group(1).strip() if m else ""


# --- the loop ----------------------------------------------------------------

def snapshot(port_dir: Path) -> dict[str, bytes]:
    return {str(p.relative_to(port_dir)): p.read_bytes()
            for p in port_dir.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def restore(port_dir: Path, snap: dict[str, bytes]) -> None:
    for p in list(port_dir.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and str(p.relative_to(port_dir)) not in snap:
            p.unlink()
    for rel, data in snap.items():
        (port_dir / rel).write_bytes(data)


@dataclass
class LoopResult:
    iterations: int
    all_pass: bool
    attempts: list[Attempt]
    final: dict[str, CaseScore]
    holdout: dict[str, CaseScore] = field(default_factory=dict)


def repair(cases: list[catalog.Case], *, client, run_dir: Path, port_dir: Path = split.PORT_DIR,
           tier: str = "B", iterations: int = 50, thinking: str = "high", who: str = "port_repair",
           holdout: list[catalog.Case] | None = None, log=print) -> LoopResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    diag = Diagnoser(port_dir, who)
    attempts: list[Attempt] = []
    failures: Counter[str] = Counter()
    scores = score(cases, port_dir, who)
    it = 0
    for it in range(1, iterations + 1):
        _log_scores(run_dir, it, scores)
        failing = [c for c in cases if not scores[c.name].passes]
        if not failing:
            it -= 1
            break
        target = failing[0]
        problem, _ = diag.diagnose(target, scores[target.name])
        consult = failures[problem.target] >= CONSULT_AFTER
        mode = "consult" if consult else "repair"
        log(f"[{it}] {target.name}: {problem.kind} {problem.target} ({mode})")
        system = (PROMPTS / f"{mode}.md").read_text()
        prompt = (consult_input(problem, [a for a in attempts if a.problem == problem.target],
                                port_dir, tier)
                  if consult else repair_input(problem, port_dir, tier))
        it_dir = run_dir / f"iter_{it:03d}"
        it_dir.mkdir(parents=True, exist_ok=True)
        (it_dir / "prompt.txt").write_text(system + "\n\n" + prompt)
        try:
            reply = argon.ask(client, input=prompt, system_instruction=system,
                              thinking_level=thinking)
        except argon.ArgonError as exc:
            if exc.reply is not None:
                exc.reply.save(it_dir)
            attempts.append(Attempt(it, mode, problem.target, "", False, f"model error: {exc}"))
            failures[problem.target] += 1
            continue
        reply.save(it_dir)
        hyp = hypothesis(reply.text)
        attempt = Attempt(it, mode, problem.target, hyp, False, "", reply.id, reply.usage)
        try:
            files = split.parse(reply.text)
            if not consult and len(files) > MAX_REPAIR_FILES:
                raise split.SplitError(f"{len(files)} files changed, at most {MAX_REPAIR_FILES} allowed")
        except split.SplitError as exc:
            attempt.reason = f"unusable reply: {exc}"
        else:
            before = snapshot(port_dir)
            try:
                written = split.write(files, port_dir)
                new_scores = score(cases, port_dir, who)
                broke = regressions(scores, new_scores)
                if broke:
                    attempt.reason = f"broke {', '.join(broke)}"
                elif new_scores[target.name].passes:
                    attempt.accepted, attempt.reason = True, f"{target.name} passes"
                else:
                    new_problem, _ = diag.diagnose(target, new_scores[target.name])
                    if new_problem.rank > problem.rank:
                        attempt.accepted = True
                        attempt.reason = (f"first problem moved to {new_problem.kind} "
                                          f"{new_problem.target}")
                    else:
                        attempt.reason = (f"no progress: first problem now {new_problem.kind} "
                                          f"{new_problem.target}")
            except Exception as exc:
                attempt.accepted = False
                attempt.reason = f"evaluation failed: {type(exc).__name__}: {exc}"
            except BaseException:
                restore(port_dir, before)
                raise
            if attempt.accepted:
                split.record(written, it_dir / "reply.txt", port_dir,
                             interaction_id=reply.id, step=mode, iteration=it)
                scores = new_scores
                failures[problem.target] = 0
            else:
                restore(port_dir, before)
        if not attempt.accepted:
            failures[problem.target] += 1
        attempts.append(attempt)
        (it_dir / "decision.json").write_text(json.dumps(asdict(attempt), indent=1) + "\n")
        log(f"[{it}] {'kept' if attempt.accepted else 'reverted'}: {attempt.reason}")

    result = LoopResult(it, all(s.passes for s in scores.values()), attempts, scores)
    if holdout:
        result.holdout = score(holdout, port_dir, who)
    (run_dir / "result.json").write_text(json.dumps(asdict(result), indent=1, default=str) + "\n")
    return result


def _log_scores(run_dir: Path, it: int, scores: dict[str, CaseScore]) -> None:
    with open(run_dir / "scoreboard.jsonl", "a") as f:
        f.write(json.dumps({"iteration": it, "scores": {n: {"ran": s.ran, "passes": s.passes,
                                                             "summary": s.summary}
                                                         for n, s in scores.items()}}) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", choices=["A", "B"], default="B")
    ap.add_argument("--case", action="append", default=[], help="limit to these training cases")
    ap.add_argument("--iterations", type=int, default=50)
    ap.add_argument("--thinking", choices=argon.THINKING_LEVELS, default="high")
    ap.add_argument("--port-dir", type=Path, default=split.PORT_DIR)
    ap.add_argument("--run-id", help="default: repair_<tier>_<UTC timestamp>")
    args = ap.parse_args()

    training = [catalog.get(n) for n in args.case] or catalog.tier_cases(args.tier)
    if any(c.tier == "holdout" for c in training):
        ap.error("holdout cases are never used for repair")
    holdout = [c for c in catalog.CASES if c.tier == "holdout"]
    run_id = args.run_id or f"repair_{args.tier}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    (RUNS / run_id).mkdir(parents=True, exist_ok=True)
    meta = {"run_id": run_id, "kind": "repair", "tier": args.tier, "model": argon.MODEL,
            "thinking": args.thinking, "iterations": args.iterations,
            "cases": [c.name for c in training]}
    (RUNS / run_id / "run.json").write_text(json.dumps(meta, indent=1) + "\n")
    result = repair(training, client=argon.make_client(), run_dir=RUNS / run_id,
                    port_dir=args.port_dir, tier=args.tier, iterations=args.iterations,
                    thinking=args.thinking, holdout=holdout)
    print(f"{run_id}: {result.iterations} iterations, "
          f"{sum(a.accepted for a in result.attempts)} patches kept, "
          f"all training cases pass: {result.all_pass}")
    for s in list(result.final.values()) + list(result.holdout.values()):
        print(s.summary or f"{s.case:20s} CRASH {s.error.strip().splitlines()[-1] if s.error else ''}")
    return 0 if result.all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
