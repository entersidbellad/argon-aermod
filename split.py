#!/usr/bin/env python3
"""Split Argon's output on ``=== FILE: path ===`` markers into port/aermod_py/.

Paths are taken relative to port/aermod_py (a leading ``port/aermod_py/`` is
dropped). Anything that would land outside that directory, is not a ``.py``
file, or would replace the human-written README is refused, so model output
can never touch the harness (in particular the frozen compare.py). A markdown
code fence wrapping a file's content is removed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
PORT_DIR = ROOT / "port" / "aermod_py"
MARKER = re.compile(r"^===\s*FILE:\s*(.+?)\s*===\s*$", re.MULTILINE)
FENCE = re.compile(r"\A```[\w+-]*[ \t]*\n(.*?)\n?```[ \t]*\Z", re.DOTALL)
PREFIX = PurePosixPath("port/aermod_py")
PROTECTED = {"README.md"}


class SplitError(ValueError):
    pass


def normalize(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw.strip().strip("`").replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SplitError(f"refusing path outside port/aermod_py: {raw!r}")
    if path.parts[:2] == PREFIX.parts:
        path = PurePosixPath(*path.parts[2:])
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path, help="raw model output")
    ap.add_argument("--out-dir", type=Path, default=PORT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        files = parse(args.input.read_text())
    except SplitError as exc:
        print(f"split.py: {exc}", file=sys.stderr)
        return 1
    for rel, content in files:
        print(f"{'would write' if args.dry_run else 'wrote'} {rel} ({content.count(chr(10))} lines)")
    if not args.dry_run:
        write(files, args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
