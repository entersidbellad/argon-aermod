"""tools/readme_results.py: the README's results block is rendered from committed files only."""

from __future__ import annotations

import pytest

import readme_results
import server


def rendered() -> str:
    return readme_results.render(server.summary(use_suite=False), server._scores("port", use_suite=False))


def test_block_reports_tier_b_in_progress_and_every_snapshot_case():
    text = rendered()
    snapshot_cases = server._scores("port", use_suite=False)["results"]
    for name in snapshot_cases:
        assert f"| `{name}` |" in text
    tier_b = server.summary(use_suite=False)["tiers"]["B"]
    if tier_b["status"] != "passing":
        assert "| B | Tier A plus PRIME building downwash |" in text and "in progress" in text


def test_block_totals_match_the_run_records():
    argon = server.summary(use_suite=False)["argon"]
    text = rendered()
    assert f"| **Total** | | | | {argon['interactions']} | {argon['usage']['total_input_tokens']:,} |" in text
    if argon["cost_usd"] is not None:
        assert f"**${argon['cost_usd']:,.2f}**" in text


def test_scores_are_called_approved_only_when_compare_also_matches_its_pinned_digest():
    summary, scores = server.summary(use_suite=False), server._scores("port", use_suite=False)
    summary["scores"]["hash_matches"] = True
    summary["compare_frozen"] = False
    assert "**not** with the approved `harness/compare.py`" in readme_results.render(summary, scores)


def test_replace_needs_the_markers_and_swaps_only_the_block():
    text = f"intro\n{readme_results.BEGIN}\nold\n{readme_results.END}\noutro\n"
    new = readme_results.replace(text, f"{readme_results.BEGIN}\nnew\n{readme_results.END}")
    assert new == f"intro\n{readme_results.BEGIN}\nnew\n{readme_results.END}\noutro\n"
    with pytest.raises(SystemExit):
        readme_results.replace("no markers", "x")
