#!/usr/bin/env python3
"""Find the module variables the ported code reads but only AERMOD's SETUP assigns.

The port gets the Fortran reachable from HRLOOP (pack.py) but not SETUP, so
every module variable that code reads without ever assigning must be handed to
it by harness/glue.py. This script:

  * lists those variables (static scan of the tier-B packed units against the
    declarations in modules.f) into harness/setup_inputs.json, and
  * with ``--fortran PATH`` writes a DUMP_SETUP subroutine that prints each of
    them; ref/build_dump.sh links it into a copy of AERMOD that calls it right
    before HRLOOP and writes SETUP.DMP, the ground truth tests/test_glue.py
    checks glue.setup_values() against.

The scan is lexical (assignment statements, DO variables, READ lists,
ALLOCATE), so a variable only ever set through a CALL argument or an IOSTAT=
specifier is reported as an input too; glue.py lists those as scratch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pack  # noqa: E402

OUT_JSON = Path(__file__).resolve().parent / "setup_inputs.json"
IDENT = re.compile(r"\b([A-Z][A-Z0-9_]*)\b")
TYPE_RE = re.compile(r"^(DOUBLE PRECISION|REAL(?:\*\d+)?|INTEGER(?:\*\d+)?|LOGICAL|"
                     r"CHARACTER(?:\s*\*\s*\(?\s*\d+\s*\)?|\s*\(\s*LEN\s*=\s*\d+\s*\))?)\s*(.*)$")
TYPE_CODE = {"DOUBLE": "D", "REAL": "D", "INTEGER": "I", "LOGICAL": "L", "CHARACTER": "C"}


@dataclass
class Var:
    name: str
    module: str
    type: str          # D (real/double), I, L, C
    rank: int
    allocatable: bool


def statements(lines: list[str]) -> list[str]:
    """Fixed-form source -> upper-case statements, continuations joined, strings blanked."""
    out: list[str] = []
    for line in lines:
        if not line.strip() or pack.is_comment(line):
            continue
        if len(line) > 5 and line[5] not in " 0" and not line[:5].strip() and out:
            out[-1] += " " + line[6:]
        else:
            out.append(line[6:])
    return [re.sub(r"'[^']*'", "''", s).split("!")[0].upper().strip() for s in out]


def split_top(text: str) -> list[str]:
    parts, depth, tok = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(tok)
            tok = ""
        else:
            tok += ch
    return parts + [tok]


def declarations() -> tuple[dict[str, Var], set[str]]:
    """Module variables in modules.f, and the names given a value there (PARAMETER/=/DATA)."""
    units = [u for u in pack.scan_file(pack.SRC / "modules.f") if u.kind == "MODULE"]
    cache: dict[str, list[str]] = {}
    found: dict[str, Var] = {}
    valued: set[str] = set()
    for u in units:
        for st in statements(pack.unit_text(u, cache).split("\n")):
            if st.startswith("DATA "):
                valued |= set(IDENT.findall(st[5:].split("/")[0]))
                continue
            if st.startswith("PARAMETER"):
                valued |= {IDENT.findall(p)[0] for p in split_top(st[st.index("(") + 1:])}
                continue
            if st.startswith("ALLOCATABLE"):
                for p in split_top(st.split("::", 1)[-1]):
                    ids = IDENT.findall(p)
                    if ids and ids[0] in found:
                        found[ids[0]].allocatable = True
                        found[ids[0]].rank = max(found[ids[0]].rank, p.count(":"))
                continue
            m = TYPE_RE.match(st)
            if not m or st.startswith(("REAL FUNCTION", "INTEGER FUNCTION")):
                continue
            attrs, _, body = m.group(2).partition("::") if "::" in m.group(2) else ("", "", m.group(2))
            if "PARAMETER" in attrs:
                valued |= {IDENT.findall(p)[0] for p in split_top(body) if IDENT.findall(p)}
                continue
            dim = re.search(r"DIMENSION\s*\(([^)]*)\)", attrs)
            for p in split_top(body):
                ids = IDENT.findall(p)
                if not ids:
                    continue
                shape = re.match(r"\s*[A-Z][A-Z0-9_]*\s*\(([^)]*)\)", p)
                dims = shape.group(1) if shape else (dim.group(1) if dim else "")
                rank = len(split_top(dims)) if dims else 0
                tcode = TYPE_CODE[m.group(1).split()[0].split("*")[0].split("(")[0]]
                found.setdefault(ids[0], Var(ids[0], u.name, tcode, rank, "ALLOCATABLE" in attrs))
                if "=" in p.split("(")[0] or re.search(r"\)\s*=|^\s*\w+\s*=", p):
                    valued.add(ids[0])
    return found, valued


def scope_usage() -> tuple[set[str], set[str]]:
    """(names referenced, names assigned) in the non-module tier-B packed units."""
    units, _ = pack.select_units("B")
    cache: dict[str, list[str]] = {}
    referenced: set[str] = set()
    assigned: set[str] = set()
    for u in units:
        if u.kind == "MODULE":
            continue
        for st in statements(pack.unit_text(u, cache).split("\n")[1:]):
            st = re.sub(r"^\d+\s+", "", st)
            referenced |= set(IDENT.findall(st))
            body = re.sub(r"^(ELSE\s+)?IF\s*\(", "(", st)
            if body.startswith("("):
                depth = 0
                for i, ch in enumerate(body):
                    depth += (ch == "(") - (ch == ")")
                    if depth == 0:
                        body = body[i + 1:].strip()
                        break
            m = re.match(r"([A-Z][A-Z0-9_]*)\s*(\([^=]*\))?\s*=(?!=)", body)
            if m:
                assigned.add(m.group(1))
            m = re.match(r"DO\s+(?:\d+\s*,?\s*)?([A-Z][A-Z0-9_]*)\s*=", body)
            if m:
                assigned.add(m.group(1))
            m = re.match(r"READ\s*\((.*?)\)\s*(.*)", body)
            if m:
                assigned |= set(IDENT.findall(m.group(2)))
            if body.startswith(("ALLOCATE", "DEALLOCATE")):
                assigned |= set(IDENT.findall(body))
    return referenced, assigned


def find_inputs() -> list[Var]:
    decl, valued = declarations()
    referenced, assigned = scope_usage()
    return [v for n, v in sorted(decl.items())
            if n in referenced and n not in assigned and n not in valued]


def fortran_dump(inputs: list[Var]) -> str:
    """Free-form DUMP_SETUP: one header line 'NAME T dims...' then one value per line."""
    fmt = {"D": "'(ES26.17E3)'", "I": "'(I0)'", "L": "'(L1)'", "C": "'(A)'"}
    mods = sorted({v.module for v in inputs})
    out = ["subroutine dump_setup()"] + [f"  use {m}" for m in mods] + [
        "  implicit none",
        "  integer :: iu",
        "  open(newunit=iu, file='SETUP.DMP', status='replace', action='write')",
    ]
    for v in inputs:
        body = [f"  write(iu,'(A,1X,A,*(1X,I0))') '{v.name}', '{v.type}', shape({v.name})",
                f"  write(iu,{fmt[v.type]}) {v.name}"]
        if v.allocatable:
            out += [f"  if (allocated({v.name})) then"] + ["  " + b for b in body] + [
                "  else", f"    write(iu,'(A,1X,A)') '{v.name}', 'UNALLOCATED'", "  end if"]
        else:
            out += body
    out += ["  close(iu)", "end subroutine dump_setup", ""]
    return "\n".join(out)


def read_dump(path: Path) -> dict[str, object]:
    """Parse SETUP.DMP into {name: scalar | ndarray (Fortran shape) | None if unallocated}."""
    lines = path.read_text(errors="replace").split("\n")
    out: dict[str, object] = {}
    i = 0
    while i < len(lines) and lines[i].strip():
        head = lines[i].split()
        i += 1
        if head[1] == "UNALLOCATED":
            out[head[0]] = None
            continue
        name, t, dims = head[0], head[1], [int(d) for d in head[2:]]
        n = int(np.prod(dims)) if dims else 1
        raw = lines[i:i + n]
        i += n
        if t == "D":
            vals = [float(x.replace("D", "E")) for x in raw]
        elif t == "I":
            vals = [int(x) for x in raw]
        elif t == "L":
            vals = [x.strip() == "T" for x in raw]
        else:
            vals = [x.rstrip() for x in raw]
        if dims:
            arr = np.array(vals, dtype=object if t == "C" else None).reshape(dims, order="F")
            out[name] = arr
        else:
            out[name] = vals[0]
    return out


def _same(value: object, ref: object) -> bool:
    if value is None or ref is None:
        return value is None and ref is None
    if isinstance(ref, np.ndarray):
        arr = np.asarray(value)
        if arr.shape != ref.shape:
            return False
        if ref.dtype == object:
            return all(str(a).rstrip() == str(b).rstrip() for a, b in zip(arr.ravel(), ref.ravel()))
        return np.array_equal(arr.astype(ref.dtype), ref)
    if isinstance(ref, str):
        return str(value).rstrip() == ref.rstrip()
    if isinstance(ref, bool) or isinstance(value, bool):
        return bool(value) is ref
    return type(ref)(value) == ref


def compare_dump(values: dict[str, object], dump: dict[str, object],
                 skip: set[str] = frozenset()) -> list[str]:
    """Names whose value differs (bit for bit) from SETUP.DMP, with the first difference."""
    problems = []
    for name, ref in dump.items():
        if name in skip:
            continue
        if name not in values:
            problems.append(f"{name}: missing")
        elif not _same(values[name], ref):
            value = values[name]
            if isinstance(ref, np.ndarray) and ref.dtype != object and value is not None \
                    and np.asarray(value).shape == ref.shape:
                arr = np.asarray(value, dtype=ref.dtype)
                idx = tuple(np.argwhere(arr != ref)[0])
                problems.append(f"{name}{list(idx)}: {arr[idx]!r} != dump {ref[idx]!r}")
            else:
                problems.append(f"{name}: {str(value)[:60]} != dump {str(ref)[:60]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fortran", type=Path, help="also write the DUMP_SETUP subroutine here")
    args = ap.parse_args()
    inputs = find_inputs()
    OUT_JSON.write_text(json.dumps([asdict(v) for v in inputs], indent=1) + "\n")
    print(f"{len(inputs)} setup inputs -> {OUT_JSON.relative_to(ROOT)}")
    if args.fortran:
        args.fortran.write_text(fortran_dump(inputs))
        print(f"wrote {args.fortran}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
