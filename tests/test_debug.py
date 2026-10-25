"""dbgparse, the DEBUGOPT catalogue and debugdiff, on real AERTEST debug files from our binary."""

from __future__ import annotations

import json
from collections import Counter

import pytest

import dbgparse
import debugdiff


pytestmark = pytest.mark.slow


def test_every_numeric_line_is_parsed(aertest_debug):
    _, skipped = aertest_debug
    assert {f: c for f, c in dbgparse.unexplained(skipped).items() if c} == {}


def test_known_values_from_aertest(aertest_debug_records):
    first = {}
    for r in aertest_debug_records:
        first.setdefault((r.sub, r.comp, r.var), r)
    zi = first[("METDEB", "", "ZI")]
    assert (zi.date, zi.isrc, zi.irec, zi.value) == (88030101, 0, 0, 37.0)
    xfinal = first[("PCALC", "", "XFINAL")]
    assert (xfinal.date, xfinal.isrc, xfinal.value, xfinal.tol) == (88030101, 1, 837.106, 0.001)
    assert first[("PSRDEB", "", "VS")].value == 15.0


def test_catalogue_is_exactly_what_aertest_prints(aertest_debug_records):
    """prompts/debug_vars.md names come from real output, not from memory."""
    entries = json.loads(debugdiff.CATALOG.read_text())
    printed = {(r.sub, r.comp, r.var) for r in aertest_debug_records}
    listed = {(e["sub"], e["comp"], e["var"]) for e in entries if "AERTEST" in e["cases"]}
    assert printed == listed
    assert printed <= debugdiff.known_names()


def test_keys_are_unique(aertest_debug_records):
    counts = Counter(r.key for r in aertest_debug_records)
    assert max(counts.values()) == 1


def _rows(records):
    return [(r.date, r.isrc, r.irec, r.comp, r.sub, r.var, r.value) for r in records]


def test_replay_matches_every_record(aertest_debug_records):
    rep = debugdiff.diff(aertest_debug_records, debugdiff.port_records(_rows(aertest_debug_records)))
    assert rep.ok and rep.n_matched == rep.n_ref == len(aertest_debug_records)


def test_first_divergence_missing_row_and_unknown_name(aertest_debug_records):
    ref = aertest_debug_records
    rows = _rows(ref)
    i = next(j for j, r in enumerate(ref) if r.var == "XFINAL" and r.value != 0)
    rows[i] = rows[i][:6] + (rows[i][6] + 3 * ref[i].tol,)
    del rows[i + 5]
    rows.append((ref[0].date, 1, 1, "PLM", "PCALC", "MADEUP", 1.0))
    rep = debugdiff.diff(ref, debugdiff.port_records(rows))
    assert rep.first_divergent.key == ref[i].key
    assert rep.first_missing.key == ref[i + 5].key
    assert rep.first_problem is rep.first_divergent
    assert rep.unknown_names == ["PCALC/PLM.MADEUP"]
    assert (rep.n_divergent, rep.n_missing, rep.n_extra) == (1, 1, 1) and not rep.ok


def test_differences_within_one_printed_unit_are_not_divergences(aertest_debug_records):
    ref = aertest_debug_records
    rows = [row[:6] + (row[6] + 0.5 * r.tol,) for row, r in zip(_rows(ref), ref)]
    assert debugdiff.diff(ref, debugdiff.port_records(rows)).ok


def test_malformed_rows_are_rejected():
    with pytest.raises(ValueError, match="has 6 fields.*'XFINAL'"):
        debugdiff.port_records([(88030101, 1, 1, "", "PCALC", "XFINAL")])
