"""split.py: confinement to port/aermod_py, fence stripping, provenance; and the port-dir guard."""

from __future__ import annotations

import json

import pytest

import split


def test_paths_with_either_prefix_land_in_the_package():
    files = split.parse("=== FILE: aermod_py/a.py ===\nA = 1\n"
                        "=== FILE: port/aermod_py/sub/b.py ===\nB = 2\n=== FILE: c.py ===\nC = 3\n")
    assert [(str(p), body) for p, body in files] == [("a.py", "A = 1\n"), ("sub/b.py", "B = 2\n"),
                                                      ("c.py", "C = 3\n")]


@pytest.mark.parametrize("path", ["../harness/compare.py", "/etc/x.py", "aermod_py/notes.md",
                                  "README.md", "aermod_py/../../x.py"])
def test_paths_outside_the_package_or_not_python_are_refused(path):
    with pytest.raises(split.SplitError):
        split.parse(f"=== FILE: {path} ===\nx = 1\n")


def test_fences_are_stripped_and_prose_before_the_first_marker_ignored():
    text = "=== HYPOTHESIS ===\nbecause\n=== FILE: aermod_py/a.py ===\n```python\nA = 1\n```\n"
    assert split.parse(text)[0][1] == "A = 1\n"


def test_no_markers_and_duplicates_are_errors():
    with pytest.raises(split.SplitError):
        split.parse("just prose")
    with pytest.raises(split.SplitError):
        split.parse("=== FILE: a.py ===\nA\n=== FILE: aermod_py/a.py ===\nB\n")


REPLY = ("=== FILE: aermod_py/__init__.py ===\nfrom .core import run_case\n"
         "=== FILE: aermod_py/core.py ===\ndef run_case(): pass\n")


def port_from_reply(tmp_path, *, saved_id="int-1", status="completed", recorded_id="int-1"):
    pkg, runs = tmp_path / "aermod_py", tmp_path / "runs"
    pkg.mkdir()
    (pkg / "README.md").write_text("human\n")
    reply = runs / "port_1" / "reply.txt"
    reply.parent.mkdir(parents=True)
    reply.write_text(REPLY)
    if saved_id is not None:
        reply.with_suffix(".json").write_text(json.dumps({"id": saved_id, "status": status}))
    meta = {"interaction_id": recorded_id} if recorded_id else {}
    split.record(split.write(split.parse(REPLY), pkg), reply, pkg, step="port", **meta)
    return pkg, runs


def test_verify_traces_files_to_recorded_replies_and_catches_hand_edits(tmp_path):
    pkg, runs = port_from_reply(tmp_path)
    assert split.verify(pkg, runs) == []

    (pkg / "core.py").write_text("def run_case(): return 1\n")
    (pkg / "extra.py").write_text("X = 1\n")
    problems = split.verify(pkg, runs)
    assert len(problems) == 2 and all("not produced" in p for p in problems)


@pytest.mark.parametrize("kwargs, why", [
    ({"recorded_id": None}, "no interaction id"),
    ({"saved_id": None}, "no reply.json"),
    ({"saved_id": "int-2"}, "does not record"),
    ({"status": "failed"}, "does not record"),
])
def test_replies_without_a_completed_interaction_vouch_for_nothing(tmp_path, kwargs, why):
    pkg, runs = port_from_reply(tmp_path, **kwargs)
    problems = split.verify(pkg, runs)
    assert len(problems) == 2 and all(why in p for p in problems)


def test_clear_keeps_the_readme(tmp_path):
    (tmp_path / "README.md").write_text("human\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.py").write_text("")
    (tmp_path / "y.py").write_text("")
    split.clear(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["README.md"]


def test_nothing_under_port_aermod_py_is_hand_written():
    """Every file but the README must be byte-identical to a recorded model reply's split."""
    assert split.verify() == []
