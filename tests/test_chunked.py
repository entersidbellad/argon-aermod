"""agent/baselines/chunked.py: every request can see where every unit is written."""

from __future__ import annotations

import pack
import port
from baselines import chunked
from conftest import SOURCE, require


def test_file_map_names_every_unit_of_every_request():
    require(SOURCE, "run python ref/fetch.py")
    counter = pack.TokenCounter()
    plan = chunked.chunks("B", 60_000, counter)
    text = chunked.file_map(plan)
    for step, units in enumerate(plan, 1):
        target = "state.py" if step == 1 else chunked.module_name(units, step)
        for u in units:
            assert f"{u.name} -> aermod_py/{target} (request {step})" in text
    request = chunked.chunk_input(plan[1], port.shared_context() + "\n\n" + text, "", 2, len(plan))
    assert "GINTRP -> aermod_py/" in request and "# Contract (prompts/contract.md)" in request
