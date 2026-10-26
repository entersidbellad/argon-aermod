"""agent/repair_loop.py end to end on AERTEST with a planted bug and a scripted fake model."""

from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest

import cases as catalog
import repair_loop
import split
from conftest import STUBS, oracle, require


class ScriptedInteractions:
    def __init__(self, replies):
        self.replies, self.inputs = list(replies), []

    def create(self, **body):
        self.inputs.append(body["input"])
        return SimpleNamespace(id=f"fake-{len(self.inputs)}", status="completed",
                               output_text=self.replies.pop(0), usage=None, errors=None)


def test_hand_written_helpers():
    assert repair_loop.hypothesis("=== HYPOTHESIS ===\nOff by one.\n=== FILE: aermod_py/a.py ===\n") \
        == "Off by one."
    src = 'def pcalc():\n    """SUBROUTINE PCALC (calc1.f)."""\n'
    assert repair_loop.units_in(src, "pcalc") == ["PCALC"]


@pytest.mark.slow
def test_rejects_a_useless_patch_then_keeps_the_fix(tmp_path):
    require(oracle("AERTEST"), "run python harness/run_ref.py AERTEST")
    require(catalog.get("AERTEST").out_dir("ref_debug") / "MODEL.DBG",
            "run python harness/run_ref.py --debug AERTEST")
    port = tmp_path / "aermod_py"
    shutil.copytree(STUBS / "buggy_port" / "aermod_py", port)
    src = (port / "__init__.py").read_text()
    noop = "=== HYPOTHESIS ===\nNothing.\n=== FILE: aermod_py/__init__.py ===\n" + src
    fix = ("=== HYPOTHESIS ===\nXFINAL carries BUG.\n=== FILE: aermod_py/__init__.py ===\n"
           + src.replace("BUG = 1.0", "BUG = 0.0"))
    client = SimpleNamespace(interactions=ScriptedInteractions([noop, fix]))

    res = repair_loop.repair([catalog.get("AERTEST")], client=client, run_dir=tmp_path / "run",
                             port_dir=port, tier="B", iterations=5, who="test_repair",
                             log=lambda *_: None)

    assert [(a.accepted, a.problem) for a in res.attempts] == [(False, "PCALC.XFINAL"),
                                                               (True, "PCALC.XFINAL")]
    assert res.attempts[0].reason.startswith("no progress")
    assert res.all_pass and res.iterations == 2
    prompt = client.interactions.inputs[0]
    assert "first problem in AERMOD's order: PCALC XFINAL[0] date=88030101" in prompt
    assert "SUBROUTINE PCALC" in prompt and "Met for this hour" in prompt
    assert split.verify(port, tmp_path / "run") == []
    assert "# Contract (prompts/contract.md)" in prompt and "# DEBUGOPT variables" in prompt
    assert "# harness/glue.py" in prompt


@pytest.mark.slow
def test_patches_that_break_evaluation_are_rolled_back(tmp_path, monkeypatch):
    require(oracle("AERTEST"), "run python harness/run_ref.py AERTEST")
    require(catalog.get("AERTEST").out_dir("ref_debug") / "MODEL.DBG",
            "run python harness/run_ref.py --debug AERTEST")
    port = tmp_path / "aermod_py"
    shutil.copytree(STUBS / "buggy_port" / "aermod_py", port)
    src = (port / "__init__.py").read_text()
    head = "=== HYPOTHESIS ===\nh\n=== FILE: aermod_py/__init__.py ===\n"
    malformed = head + src.replace("r[:6] + (r[6] + BUG,)", "r[:6]")
    explodes = head + src + "\n# evaluation of this patch raises\n"
    fix = head + src.replace("BUG = 1.0", "BUG = 0.0")
    client = SimpleNamespace(interactions=ScriptedInteractions([malformed, explodes, fix]))

    real_regressions, calls = repair_loop.regressions, []

    def regressions(before, after):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real_regressions(before, after)

    monkeypatch.setattr(repair_loop, "regressions", regressions)
    after_each = []
    res = repair_loop.repair([catalog.get("AERTEST")], client=client, run_dir=tmp_path / "run",
                             port_dir=port, tier="B", iterations=5, who="test_repair_rollback",
                             log=lambda msg: after_each.append((port / "__init__.py").read_text())
                             if "reverted" in msg else None)

    assert [a.accepted for a in res.attempts] == [False, False, True]
    assert res.attempts[0].reason.startswith("no progress: first problem now crash")
    assert res.attempts[1].reason == "evaluation failed: RuntimeError: boom"
    assert after_each == [src, src]
    assert res.all_pass and split.verify(port, tmp_path / "run") == []


CIRCULAR = '''Traceback (most recent call last):
  File "/workspace/harness/run_port.py", line 120, in run_staged
    port = load_port(package_dir)
  File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
  File "{pkg}/__init__.py", line 2, in <module>
    from .hrloop import run_case
  File "{pkg}/hrloop.py", line 4, in <module>
    from .calc1 import pcalc
  File "{pkg}/calc1.py", line 3, in <module>
    from .hrloop import grid
ImportError: cannot import name 'grid' from partially initialized module 'aermod_py.hrloop' (most likely due to a circular import) ({pkg}/hrloop.py)
'''


def small_port(tmp_path, **files):
    pkg = tmp_path / "aermod_py"
    pkg.mkdir()
    for name, text in {"__init__.py": "from .hrloop import run_case\n", **files}.items():
        (pkg / name).write_text(text)
    return pkg


def test_import_crash_packets_show_every_module_in_the_traceback(tmp_path):
    pkg = small_port(tmp_path, **{"hrloop.py": "from .calc1 import pcalc\n",
                                  "calc1.py": "from .hrloop import grid\n", "other.py": "X = 1\n"})
    error = CIRCULAR.format(pkg=pkg)
    assert repair_loop.files_in_traceback(error, pkg) == ["calc1.py", "hrloop.py", "__init__.py"]
    problem = repair_loop.crash_problem(catalog.get("AERTEST"), error, pkg)
    packet, _ = repair_loop.repair_packet(problem, pkg, "A")
    for name in ("calc1.py", "hrloop.py", "__init__.py"):
        assert f"# Current Python: aermod_py/{name}" in packet
    assert "other.py" not in packet


def test_packets_never_exceed_the_cap(tmp_path):
    count = len
    pkg = small_port(tmp_path, **{"hrloop.py": "a" * 500, "calc1.py": "b" * 5000})
    problem = repair_loop.Problem("AERTEST", "crash", "boom", files=("hrloop.py", "calc1.py"))
    packet, size = repair_loop.repair_packet(problem, pkg, "A", count, limit=1000)
    assert size <= 1000 and size == count(packet)
    assert "aermod_py/hrloop.py\n" in packet and "Not shown (packet size cap): aermod_py/calc1.py" in packet
    with pytest.raises(repair_loop.PacketTooLarge):
        repair_loop.repair_packet(problem, pkg, "A", count, limit=400)


def fake_scores(passing):
    return lambda cases, port_dir, who: {
        c.name: repair_loop.CaseScore(c.name, True, c.name in passing) for c in cases}


def test_stop_at_passing_stops_before_any_request(tmp_path, monkeypatch):
    cases = [catalog.get("CAPPED_STACK2"), catalog.get("AERTEST")]
    monkeypatch.setattr(repair_loop, "score", fake_scores({"CAPPED_STACK2"}))
    client = SimpleNamespace(interactions=ScriptedInteractions([]))
    res = repair_loop.repair(cases, client=client, run_dir=tmp_path / "run",
                             port_dir=small_port(tmp_path), stop_at_passing=1, log=lambda *_: None)
    assert (res.iterations, res.stop_reason, client.interactions.inputs) == (0, "1 cases pass", [])


def test_budget_stops_before_a_request_it_cannot_afford(tmp_path, monkeypatch):
    monkeypatch.setattr(repair_loop, "score", fake_scores(set()))
    monkeypatch.setattr(repair_loop.Diagnoser, "diagnose", lambda self, case, s: (
        repair_loop.Problem(case.name, "crash", "boom", rank=(-1,)), None))
    client = SimpleNamespace(interactions=ScriptedInteractions([]))
    prices = repair_loop.argon.Prices(input=1000.0, output=1000.0)
    res = repair_loop.repair([catalog.get("AERTEST")], client=client, run_dir=tmp_path / "run",
                             port_dir=small_port(tmp_path), budget_usd=1.0, prices=prices,
                             counter=len, log=lambda *_: None)
    assert res.stop_reason.startswith("budget: $0.00 spent") and client.interactions.inputs == []
    with pytest.raises(ValueError):
        repair_loop.repair([], client=client, run_dir=tmp_path / "r2", budget_usd=1.0)


def test_spend_is_priced_from_usage():
    prices = repair_loop.argon.Prices(input=2.0, output=10.0)
    usage = {"total_input_tokens": 1_000_000, "total_output_tokens": 100_000,
             "total_thought_tokens": 50_000}
    assert prices.cost(usage) == pytest.approx(2.0 + 1.5)
