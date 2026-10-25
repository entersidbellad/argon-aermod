"""harness/run_port.py with stub ports: byte-exact replay, result checks, fresh imports."""

from __future__ import annotations

import os
import textwrap

import pytest

import cases as catalog
import run_port
from conftest import STUBS, oracle, require


def data_rows(path):
    return [l for l in path.read_text().splitlines() if l.strip() and not l.startswith("*")]


@pytest.mark.parametrize("name", ["AERTEST", "HRDOW_STACK1", "FLATELEV_FLAT_STK"])
def test_replayed_oracle_is_written_byte_for_byte(name):
    ref = require(oracle(name), f"run python harness/run_ref.py {name}")
    run = run_port.run_case(catalog.get(name), who="test_port_replay",
                            package_dir=STUBS / "replay_port")
    assert run.ok, run.error
    assert data_rows(run.workdir / catalog.POSTFILE_NAME) == data_rows(ref)


def test_debug_rows_are_pickled():
    require(oracle("AERTEST"), "run python harness/run_ref.py AERTEST")
    run = run_port.run_case(catalog.get("AERTEST"), debug=True, who="test_port_zero",
                            package_dir=STUBS / "zero_port")
    assert run.ok, run.error
    assert (run.workdir / run_port.DEBUG_FILE).exists()


def test_outputs_are_stamped_with_the_package_version(tmp_path):
    require(oracle("CAPPED_STACK2"), "run python harness/run_ref.py CAPPED_STACK2")
    pkg = tmp_path / "zero_port"
    pkg.mkdir()
    (pkg / "__init__.py").write_bytes((STUBS / "zero_port" / "__init__.py").read_bytes())
    before = run_port.package_sha256(pkg)
    run = run_port.run_case(catalog.get("CAPPED_STACK2"), who="test_port_stamp", package_dir=pkg)
    assert run.ok, run.error
    assert (run.workdir / run_port.PORT_HASH_FILE).read_text().strip() == before
    (pkg / "extra.py").write_text("X = 1\n")
    assert run_port.package_sha256(pkg) != before


def make_port(tmp_path, body: str):
    pkg = tmp_path / "aermod_py"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text(textwrap.dedent(body))
    return pkg


BAD_PORTS = {
    "dates": ("dates = glue.expected_dates(project, met)[1:]\n"
              "conc = np.zeros((len(dates), len(project.receptors)))", "dates differ"),
    "shape": ("dates = glue.expected_dates(project, met)\n"
              "conc = np.zeros((len(dates), 3))", "shape"),
    "dtype": ("dates = glue.expected_dates(project, met)\n"
              "conc = np.zeros((len(dates), len(project.receptors)), dtype=np.float32)", "float64"),
    "nan": ("dates = glue.expected_dates(project, met)\n"
            "conc = np.full((len(dates), len(project.receptors)), np.nan)", "non-finite"),
}


@pytest.mark.parametrize("kind", sorted(BAD_PORTS))
def test_malformed_results_are_rejected(tmp_path, kind):
    require(oracle("AERTEST"), "run python harness/run_ref.py AERTEST")
    code, message = BAD_PORTS[kind]
    pkg = make_port(tmp_path, "import numpy as np\nimport glue\n\n"
                    "def run_case(project, met, setup, *, debug=False):\n"
                    + textwrap.indent(code, "    ") + "\n    return glue.Result(dates=dates, conc=conc)\n")
    run = run_port.run_case(catalog.get("AERTEST"), who="test_port_bad", package_dir=pkg)
    assert not run.ok and message in run.error
    assert (run.workdir / run_port.ERROR_FILE).exists()


def test_missing_port_is_reported(tmp_path):
    require(oracle("AERTEST"), "run python harness/run_ref.py AERTEST")
    run = run_port.run_case(catalog.get("AERTEST"), who="test_port_none", package_dir=tmp_path / "aermod_py")
    assert not run.ok and "has not been generated" in run.error


def test_rewritten_file_is_reimported_even_with_same_size_and_mtime(tmp_path):
    pkg = make_port(tmp_path, "VALUE = 1\ndef run_case(*a, **k): pass\n")
    init = pkg / "__init__.py"
    assert run_port.load_port(pkg).VALUE == 1
    stat = init.stat()
    init.write_text("VALUE = 2\ndef run_case(*a, **k): pass\n")
    os.utime(init, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert run_port.load_port(pkg).VALUE == 2
