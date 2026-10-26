#!/usr/bin/env python3
"""Split Argon's output on ``=== FILE: path ===`` markers into port/aermod_py/.

Paths are taken relative to port/aermod_py (a leading ``port/aermod_py/`` or
``aermod_py/``, the form prompts/contract.md asks for, is dropped). Anything that would land outside that directory, is not a ``.py``
file, or would replace the human-written README is refused, so model output
can never touch the harness (in particular the frozen compare.py). A markdown
code fence wrapping a file's content is removed.

Provenance: ``record`` writes files.json next to the saved model reply (under
agent/runs/), and ``verify`` checks that every file in port/aermod_py except
the README is byte-identical to what splitting some recorded reply produces,
and that the reply belongs to a completed Argon interaction saved by agent/,
which is how the tests prove no Python under port/ was written by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
PORT_DIR = ROOT / "port" / "aermod_py"
MARKER = re.compile(r"^===\s*FILE:\s*(.+?)\s*===\s*$", re.MULTILINE)
FENCE = re.compile(r"\A```[\w+-]*[ \t]*\n(.*?)\n?```[ \t]*\Z", re.DOTALL)
PREFIXES = (("port", "aermod_py"), ("aermod_py",))
PROTECTED = {"README.md"}
RUNS_DIR = ROOT / "agent" / "runs"
MANIFEST = "files.json"


class SplitError(ValueError):
    pass


def normalize(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw.strip().strip("`").replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SplitError(f"refusing path outside port/aermod_py: {raw!r}")
    for prefix in PREFIXES:
        if path.parts[:len(prefix)] == prefix:
            path = PurePosixPath(*path.parts[len(prefix):])
            break
    if not path.parts or path.suffix != ".py":
        raise SplitError(f"only .py files may be written, got {raw!r}")
    if str(path) in PROTECTED:
        raise SplitError(f"{raw!r} is human-owned and may not be overwritten")
    return path


def parse(text: str) -> list[tuple[PurePosixPath, str]]:
    markers = list(MARKER.finditer(text))
    if not markers:
        raise SplitError("no '=== FILE: path ===' markers found")
    files: list[tuple[PurePosixPath, str]] = []
    seen: set[PurePosixPath] = set()
    for i, m in enumerate(markers):
        path = normalize(m.group(1))
        if path in seen:
            raise SplitError(f"{path} appears twice")
        seen.add(path)
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        body = text[m.end():end].strip("\n")
        fenced = FENCE.match(body.strip())
        if fenced:
            body = fenced.group(1)
        files.append((path, body.rstrip() + "\n"))
    return files


def write(files: list[tuple[PurePosixPath, str]], out_dir: Path = PORT_DIR) -> list[Path]:
    out_dir = out_dir.resolve()
    written = []
    for rel, content in files:
        dest = (out_dir / rel).resolve()
        if out_dir not in dest.parents:
            raise SplitError(f"{rel} resolves outside {out_dir}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        written.append(dest)
    return written


def clear(out_dir: Path = PORT_DIR) -> None:
    """Remove everything under out_dir except the human-owned files, before a fresh port."""
    for path in sorted(out_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.relative_to(out_dir).as_posix() in PROTECTED:
            continue
        path.rmdir() if path.is_dir() else path.unlink()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(written: list[Path], reply: Path, out_dir: Path = PORT_DIR, **meta) -> Path:
    """Write files.json beside ``reply``: which files splitting it produced, with hashes."""
    out_dir = out_dir.resolve()
    manifest = reply.parent / MANIFEST
    entries = json.loads(manifest.read_text()) if manifest.exists() else []
    entries.append({"reply": reply.name, **meta,
                    "files": {str(p.resolve().relative_to(out_dir)): sha256(p) for p in written}})
    manifest.write_text(json.dumps(entries, indent=1) + "\n")
    return manifest


def _interaction_problem(entry: dict, reply: Path) -> str | None:
    """Why a manifest entry is not backed by a completed, saved Argon interaction."""
    if not entry.get("interaction_id"):
        return f"{reply.name} has no interaction id (split by hand, not by agent/)"
    meta_path = reply.with_suffix(".json")
    if not meta_path.is_file():
        return f"{reply.name} has no {meta_path.name} from argon.Reply.save"
    meta = json.loads(meta_path.read_text())
    if meta.get("id") != entry["interaction_id"] or meta.get("status") != "completed":
        return f"{meta_path.name} does not record completed interaction {entry['interaction_id']}"
    return None


def trace(port_dir: Path = PORT_DIR, runs_dir: Path = RUNS_DIR) -> list[dict]:
    """For every file in port_dir but the README: the reply and Argon interaction that
    produced it, or ``problem`` saying why it is not traceable.

    A reply counts only if its manifest entry names an interaction id that the
    reply's saved metadata (``<stem>.json``) records as completed, so running
    this script by hand on some text file never vouches for its output.
    """
    recorded: dict[tuple[str, str], tuple[Path, dict]] = {}
    rejected: dict[tuple[str, str], str] = {}
    for manifest in sorted(runs_dir.rglob(MANIFEST)):
        for entry in json.loads(manifest.read_text()):
            reply = manifest.parent / entry["reply"]
            why = _interaction_problem(entry, reply)
            for rel, digest in entry["files"].items():
                if why is None:
                    recorded.setdefault((rel, digest), (reply, entry))
                else:
                    rejected.setdefault((rel, digest), why)
    out = []
    for path in sorted(p for p in port_dir.rglob("*") if p.is_file()):
        rel = str(path.relative_to(port_dir))
        if rel in PROTECTED or "__pycache__" in path.parts:
            continue
        key = (rel, sha256(path))
        row = {"file": rel, "sha256": key[1], "reply": None, "interaction_id": None,
               "step": None, "problem": None}
        out.append(row)
        if key not in recorded:
            row["problem"] = rejected.get(key) or "not produced by any recorded model reply"
            continue
        reply, entry = recorded[key]
        row.update(reply=reply.relative_to(runs_dir).as_posix(),
                   interaction_id=entry["interaction_id"], step=entry.get("step"))
        produced = dict((str(r), body) for r, body in parse(reply.read_text()))
        if produced.get(rel) != path.read_text():
            row["problem"] = f"differs from what {row['reply']} splits into"
    return out


def verify(port_dir: Path = PORT_DIR, runs_dir: Path = RUNS_DIR) -> list[str]:
    """Problems with port_dir's provenance; empty means every file came from a recorded reply."""
    return [f"{t['file']}: {t['problem']}" for t in trace(port_dir, runs_dir) if t["problem"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path, nargs="?", help="raw model output")
    ap.add_argument("--out-dir", type=Path, default=PORT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="check every file in --out-dir came from a recorded reply")
    args = ap.parse_args()
    if args.verify:
        problems = verify(args.out_dir)
        for p in problems:
            print(f"split.py: {p}", file=sys.stderr)
        if not problems:
            n = sum(1 for p in args.out_dir.rglob("*.py") if "__pycache__" not in p.parts)
            print(f"{args.out_dir}: " + (f"{n} Python files, all from recorded Argon interactions"
                                         if n else "no Python files yet"))
        return 1 if problems else 0
    if args.input is None:
        ap.error("give the model output file, or --verify")
    try:
        files = parse(args.input.read_text())
    except SplitError as exc:
        print(f"split.py: {exc}", file=sys.stderr)
        return 1
    for rel, content in files:
        print(f"{'would write' if args.dry_run else 'wrote'} {rel} ({content.count(chr(10))} lines)")
    if not args.dry_run:
        record(write(files, args.out_dir), args.input.resolve(), args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
