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
