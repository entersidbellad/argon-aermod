"""The prompts only name things that exist: real DEBUGOPT names, real glue attributes."""

from __future__ import annotations

import json
import re

import pytest

import glue
import port
from conftest import ROOT

PROMPTS = ROOT / "prompts"
CATALOG = json.loads((ROOT / "harness" / "debug_vars.json").read_text())
VARS = {e["var"] for e in CATALOG}
SUBS = {e["sub"] for e in CATALOG}
KEY_WORDS = {"KURDAT", "ISRC", "IREC", "PAN", "PLM", "PRIME"}
TICKED = re.compile(r"`([A-Z][A-Z0-9_.*()/+-]*)`")


def section(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end)]


def test_contract_debug_names_come_from_real_aermod_output():
    contract = (PROMPTS / "contract.md").read_text()
    names = set(TICKED.findall(section(contract, "## Debug rows", "## How the port")))
    unknown = {n for n in names - VARS - SUBS - KEY_WORDS
               if not (n.endswith("*") and any(v.startswith(n[:-1]) for v in VARS))}
    assert unknown == set()


def test_catalogue_header_examples_are_catalogued():
    header = (PROMPTS / "debug_vars.md").read_text().split("## METEOR.DBG")[0]
    names = set(TICKED.findall(header)) - KEY_WORDS
    assert names <= VARS


@pytest.mark.parametrize("prompt", ["port.md", "repair.md", "consult.md", "chunked_port.md"])
def test_other_prompts_name_no_unverified_debug_variables(prompt):
    text = (PROMPTS / prompt).read_text()
    for stale in ("USTAR", "DHF", "SZEFF", "QSUBC", "intermediates", "sources=None"):
        assert stale not in text


def test_glue_attributes_named_in_the_contract_exist():
    contract = (PROMPTS / "contract.md").read_text()
    for name in set(re.findall(r"\bglue\.([A-Za-z_]+)", contract)) - {"py"}:
        assert hasattr(glue, name), name


def test_full_prompt_has_every_part():
    if not (ROOT / "context" / "tier_B_code.txt").exists():
        pytest.skip("context/tier_B_code.txt missing; run python pack.py")
    text = port.build_input("B")
    for part in ("Contract", "harness/glue.py", "SETUP inputs", "DEBUGOPT variables", "Fortran, tier B"):
        assert part in text
    assert "SUBROUTINE HRLOOP" in text and "| `AXS` |" in text
    assert "comment lines removed" in text
    assert "comment lines removed" not in port.build_input("B", with_comments=True)


@pytest.mark.parametrize("max_out, times", [(None, 1), (65_536, 1), (65_537, 2), (262_144, 4)])
def test_input_billing_multiplier(max_out, times):
    assert port.input_multiplier(max_out) == times
