"""Shared paths, skips and session fixtures.

Most tests run against real artefacts that are not committed (EPA source, our
compiled binaries, their outputs). Each test skips, saying what to run, when
its artefact is missing:

    make ref          # python ref/fetch.py && ref/build.sh && ref/build_dump.sh
    make refs         # out/ref
    make debug-refs   # out/ref_debug (AERTEST, aertest_nobldg)
    make dumps        # out/setup_dump/<case>/SETUP.DMP
    python pack.py    # context/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "harness", ROOT / "agent"):
    sys.path.insert(0, str(p))

import cases as catalog  # noqa: E402
import dbgparse  # noqa: E402

STUBS = ROOT / "tests" / "stub_ports"
BINARY = ROOT / "ref" / "aermod"
DUMP_BINARY = ROOT / "ref" / "aermod_dump"
SOURCE = ROOT / "ref" / "aermod_source" / "aermod_source_v26135"


def oracle(name: str) -> Path:
    return catalog.get(name).postfile("ref")


def require(path: Path, how: str) -> Path:
    if not path.exists():
        pytest.skip(f"{path.relative_to(ROOT)} missing; {how}")
    return path


def cases_with(who: str, filename: str) -> list[str]:
    return [c.name for c in catalog.CASES if (c.out_dir(who) / filename).exists()]


@pytest.fixture(scope="session")
def aertest_debug() -> tuple[list[dbgparse.Record], dict]:
    """AERTEST's parsed DEBUGOPT records and the per-file templates of skipped lines."""
    workdir = catalog.get("AERTEST").out_dir("ref_debug")
    require(workdir / "MODEL.DBG", "run python harness/run_ref.py --debug AERTEST")
    skipped: dict = {}
    return dbgparse.parse_dir(workdir, skipped), skipped


@pytest.fixture(scope="session")
def aertest_debug_records(aertest_debug) -> list[dbgparse.Record]:
    return aertest_debug[0]
