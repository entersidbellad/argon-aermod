#!/usr/bin/env python3
"""Fetch AERMOD 26135 source and the in-scope slice of EPA's test-case package.

The source zip (~0.7 MB) is downloaded whole. The test-case zip is ~490 MB, so
only the members listed in ``testcase_manifest.txt`` are pulled, using HTTP
range requests against the zip's central directory. Every extracted file is
checked against ``checksums.sha256``; pass ``--update-checksums`` to rewrite it
(do that only when deliberately moving to a new EPA release).

EPA's zips unpack read-only, so everything extracted is made user-writable.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_URL = "https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod"
SOURCE_URL = f"{BASE_URL}/aermod_source.zip"
TESTCASE_URL = f"{BASE_URL}/aermod_test_cases.zip"
TEST_SET = "aermet26135_aermod26135"
SOURCE_DIR = HERE / "aermod_source"
TESTCASE_DIR = HERE / "epa_testcases"
MANIFEST = HERE / "testcase_manifest.txt"
CHECKSUMS = HERE / "checksums.sha256"


class HttpRangeFile:
    """Seekable read-only view of a remote file, fetched in cached 1 MiB blocks."""

    BLOCK = 1 << 20

    def __init__(self, url: str):
        self.url = url
        self.pos = 0
        self._cache: dict[int, bytes] = {}
        head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
        self.size = int(head.headers["Content-Length"])
        self.last_modified = head.headers.get("Last-Modified", "")

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def _block(self, index: int) -> bytes:
        if index not in self._cache:
            start = index * self.BLOCK
            end = min(start + self.BLOCK, self.size) - 1
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}"})
            for attempt in range(4):
                try:
                    self._cache[index] = urllib.request.urlopen(req, timeout=120).read()
                    break
                except OSError:
                    if attempt == 3:
                        raise
        return self._cache[index]

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            index, offset = divmod(self.pos, self.BLOCK)
            chunk = self._block(index)[offset:offset + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_writable(root: Path) -> None:
    """Equivalent of ``chmod -R u+w``."""
    for p in [root, *root.rglob("*")]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)


def load_checksums() -> dict[str, str]:
    if not CHECKSUMS.exists():
        return {}
    out = {}
    for line in CHECKSUMS.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split(maxsplit=1)
            out[rel.strip()] = digest
    return out


def read_manifest() -> list[str]:
    return [
        line.strip() for line in MANIFEST.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def fetch_source() -> Path:
    zpath = HERE / "aermod_source.zip"
    if not zpath.exists():
        print(f"downloading {SOURCE_URL}")
        urllib.request.urlretrieve(SOURCE_URL, zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(SOURCE_DIR)
    make_writable(SOURCE_DIR)
    return zpath


def fetch_testcases() -> tuple[int, str]:
    wanted = read_manifest()
    remote = HttpRangeFile(TESTCASE_URL)
    with zipfile.ZipFile(remote) as z:
        names = set(z.namelist())
        missing = [m for m in wanted if f"{TEST_SET}/{m}" not in names]
        if missing:
            sys.exit(f"members not in EPA zip: {missing}")
        for member in wanted:
            dest = TESTCASE_DIR / member
            if dest.exists():
                continue
            print(f"  extracting {member}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(f"{TEST_SET}/{member}") as src, open(dest, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
    make_writable(TESTCASE_DIR)
    return remote.size, remote.last_modified


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update-checksums", action="store_true",
                    help="rewrite checksums.sha256 from the files just fetched")
    args = ap.parse_args()

    src_zip = fetch_source()
    print(f"source: {SOURCE_DIR}")
    size, modified = fetch_testcases()
    print(f"test cases: {TESTCASE_DIR} (remote zip {size} bytes, Last-Modified {modified})")

    current = {"aermod_source.zip": sha256(src_zip)}
    for f in sorted((SOURCE_DIR).rglob("*.f")):
        current[str(f.relative_to(HERE))] = sha256(f)
    for member in read_manifest():
        current[f"epa_testcases/{member}"] = sha256(TESTCASE_DIR / member)

    if args.update_checksums:
        header = (
            f"# AERMOD 26135 from {BASE_URL}\n"
            f"# aermod_test_cases.zip: {size} bytes, Last-Modified {modified}"
            " (only manifest members are fetched)\n"
        )
        CHECKSUMS.write_text(header + "".join(f"{d}  {p}\n" for p, d in current.items()))
        print(f"wrote {CHECKSUMS} ({len(current)} entries)")
        return 0

    expected = load_checksums()
    if not expected:
        sys.exit("checksums.sha256 missing; run with --update-checksums")
    bad = [p for p, d in current.items() if expected.get(p) != d]
    bad += [p for p in expected if p not in current]
    if bad:
        print("CHECKSUM MISMATCH:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print(f"all {len(current)} checksums match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
