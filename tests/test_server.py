"""server.py: read-only endpoints over agent/runs, out/suite_*.json and split provenance."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import server
import split


@pytest.fixture
def client(tmp_path, monkeypatch):
    runs, out, port, results = (tmp_path / d for d in ("runs", "out", "aermod_py", "results"))
    for d in (runs, out, port, results):
        d.mkdir()
    (port / "README.md").write_text("readme\n")
    monkeypatch.setattr(server, "RUNS_DIR", runs)
    monkeypatch.setattr(server, "OUT_DIR", out)
    monkeypatch.setattr(server, "PORT_DIR", port)
    monkeypatch.setattr(server, "RESULTS_DIR", results)
    return TestClient(server.app)


def write_run(runs, run_id, meta, replies):
    run_dir = runs / run_id
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps(meta))
    for i, usage in enumerate(replies):
        sub = run_dir / f"iter_{i:03d}"
        sub.mkdir()
        (sub / "reply.json").write_text(json.dumps(
            {"id": f"int-{i}", "status": "completed", "seconds": 1.0, "usage": usage, "errors": []}))
    return run_dir


def test_runs_sum_output_tokens_over_every_reply(client):
    write_run(server.RUNS_DIR, "repair_B_x", {"kind": "repair", "tier": "B", "model": "m"},
              [{"total_output_tokens": 10}, {"total_output_tokens": 5, "total_thought_tokens": 2}])
    (run,) = client.get("/api/runs").json()
    assert (run["id"], run["kind"], run["tier"], run["replies"], run["output_tokens"]) == \
        ("repair_B_x", "repair", "B", 2, 15)
    assert run["usage"]["total_thought_tokens"] == 2
    detail = client.get("/api/runs/repair_B_x").json()
    assert len(detail["interactions"]) == 2 and detail["run"]["model"] == "m"


@pytest.mark.parametrize("bad", ["..", "nope", ".hidden"])
def test_unknown_or_escaping_run_ids_are_404(client, bad):
    assert client.get(f"/api/runs/{bad}").status_code == 404


def test_no_endpoint_starts_anything(client):
    assert client.post("/api/run").status_code in (404, 405)
    assert client.post("/api/certify").status_code in (404, 405)


def suite(results, compare_sha256, port_sha256=None):
    server.OUT_DIR.joinpath("suite_port.json").write_text(json.dumps(
        {"who": "port", "time": "t", "compare_sha256": compare_sha256,
         "port_sha256": port_sha256, "results": results}))


def passing(case):
    return {"case": case, "passes": True, "epa": {"passes": True}, "strict": {"passes": True}}


def test_test_results_flag_a_suite_scored_with_another_compare(client):
    assert client.get("/api/test-results").json()["suite_found"] is False
    suite([passing("CAPPED_STACK2")], "0" * 64)
    data = client.get("/api/test-results").json()
    assert data["suite_found"] and not data["hash_matches"]
    row = data["results"]["CAPPED_STACK2"]
    assert (row["passes"], row["epa_pass"], row["strict_pass"], row["error"]) == \
        (True, True, True, None)
    assert "AERTEST" in data["tier_b"] and "AERTEST" not in data["tier_a"]
    assert "TESTPM10" in data["holdout"]
    assert client.get("/api/test-results", params={"who": "../x"}).status_code == 400


def test_certify_needs_every_criterion(client):
    tier_a = client.get("/api/test-results").json()["tier_a"]
    suite([passing(c) for c in tier_a], server.compare_hash())
    cert = client.get("/api/certify").json()
    by_name = {c["name"]: c["ok"] for c in cert["criteria"]}
    assert by_name["compare_frozen"] and by_name["tier_a_epa"] and by_name["tier_a_strict"]
    assert not by_name["port_exists"] and not cert["certified"]

    (server.PORT_DIR / "__init__.py").write_text("hand written\n")
    cert = client.get("/api/certify").json()
    by_name = {c["name"]: c["ok"] for c in cert["criteria"]}
    assert by_name["port_exists"] and not by_name["provenance"] and not cert["certified"]


def test_provenance_of_the_real_port_dir_is_clean():
    assert TestClient(server.app).get("/api/provenance").json()["problems"] == []


def port_from_argon(run_id, body):
    """Install a package exactly as agent/port.py would, provenance included."""
    run_dir = server.RUNS_DIR / run_id
    run_dir.mkdir()
    reply = run_dir / "reply.txt"
    reply.write_text(f"=== FILE: aermod_py/__init__.py ===\n{body}")
    (run_dir / "reply.json").write_text(json.dumps({"id": run_id, "status": "completed",
                                                    "usage": {}}))
    split.clear(server.PORT_DIR)
    written = split.write(split.parse(reply.read_text()), server.PORT_DIR)
    split.record(written, reply, server.PORT_DIR, interaction_id=run_id, step="port")


def test_certification_is_tied_to_the_port_version_that_was_scored(client):
    port_from_argon("port_1", "def run_case(*a, **k): pass\n")
    tier_a = client.get("/api/test-results").json()["tier_a"]
    suite([passing(c) for c in tier_a], server.compare_hash(), server.port_hash())
    assert client.get("/api/certify").json()["certified"] is True

    port_from_argon("port_2", "def run_case(*a, **k): return None\n")
    cert = client.get("/api/certify").json()
    by_name = {c["name"]: c["ok"] for c in cert["criteria"]}
    assert by_name["provenance"] and by_name["compare_frozen"]
    assert not by_name["scored_this_port"] and not cert["certified"]
    assert client.get("/api/test-results").json()["port_matches"] is False


def test_tier_a_stamps_certify_even_when_tier_b_cases_were_never_ported(client):
    port_from_argon("port_1", "def run_case(*a, **k): pass\n")
    data = client.get("/api/test-results").json()
    stamped = [{**passing(c), "port_sha256": server.port_hash()} for c in data["tier_a"]]
    missing = [{"case": c, "passes": False, "error": "missing"} for c in data["tier_b"]]
    suite(stamped + missing, server.compare_hash(), port_sha256=None)
    assert client.get("/api/test-results").json()["port_matches"] is True
    assert client.get("/api/certify").json()["certified"] is True


def box_repair_run(runs):
    """agent/runs/repair_A_box/step_001 exactly as repair_loop.repair laid it out on the box."""
    step = runs / "repair_A_box" / "step_001"
    it = step / "iter_001"
    it.mkdir(parents=True)
    usage = {"total_input_tokens": 1250, "total_output_tokens": 1014,
             "total_thought_tokens": 11433, "total_tokens": 13697}
    (it / "reply.json").write_text(json.dumps(
        {"id": "v1_fix", "status": "completed", "seconds": 139.6, "usage": usage, "errors": []}))
    (it / "files.json").write_text(json.dumps([{"reply": "reply.txt", "interaction_id": "v1_fix",
                                                "step": "repair", "iteration": 1,
                                                "files": {"__init__.py": "0" * 64}}]))
    attempt = {"iteration": 1, "mode": "repair", "problem": "crash:", "hypothesis": "circular import",
               "accepted": True, "reason": "aertest_nobldg passes", "interaction_id": "v1_fix",
               "usage": usage}
    (it / "decision.json").write_text(json.dumps(attempt))
    final = {c: {"case": c, "ran": True, "passes": True, "error": "", "summary": f"{c} PASS"}
             for c in ("aertest_nobldg", "CAPPED_STACK2")}
    (step / "result.json").write_text(json.dumps(
        {"iterations": 1, "all_pass": True, "attempts": [attempt], "final": final, "holdout": {}}))
    (step / "scoreboard.jsonl").write_text("{}\n")


def test_nested_repair_run_without_run_json_is_listed(client):
    box_repair_run(server.RUNS_DIR)
    (run,) = client.get("/api/runs").json()
    assert (run["id"], run["kind"], run["tier"], run["patches_kept"], run["cases_passing"]) == \
        ("repair_A_box/step_001", "repair", "A", 1, 2)
    (inter,) = run["interactions"]
    assert (inter["step"], inter["iteration"], inter["files"]) == ("repair", 1, ["__init__.py"])
    assert inter["decision"]["accepted"] and inter["decision"]["hypothesis"] == "circular import"
    assert client.get("/api/runs/repair_A_box/step_001").json()["result"]["all_pass"] is True
    assert client.get("/api/runs/repair_A_box").status_code == 404
    assert client.get("/api/runs/repair_A_box/step_001/iter_001").status_code == 404
    data = client.get("/api/test-results").json()
    assert data["source"] == "agent/runs/repair_A_box/step_001/result.json"
    assert data["results"]["CAPPED_STACK2"]["summary"] == "CAPPED_STACK2 PASS"


SNAPSHOT = """# Tier A results: gemini-4-argon port of AERMOD 26135

Strict comparison (harness/compare.py,
sha256 `{digest}`). Scored 2026-10-25 14:09 PDT on harness `f53f81f`.

| Case | Role | Result | Slope (best-fit) | Zero/nonzero | P99 rel err | H4H fails | Stable hrs | Convective hrs |
|---|---|---|---|---|---|---|---|---|
| aertest_nobldg | training | PASS | 1.000000/1.000000/1.000000 | 100.000% | 0.00e+00 | 0/144 | 100.00%(64h) | 100.00%(32h) |
| testpm10_stack2 | holdout | PASS | 1.000000/0.999990/1.000000 | 99.500% | 2.00e-05 | 0/36 | 100.00%(20926h) | 100.00%(22898h) |

## Argon calls

| Step | Interaction ID | Packet (count_tokens) | Billed input | Output | Thinking | Cost |
|---|---|---|---|---|---|---|
| Repair 1: circular import hrloop <-> metext (`__init__.py`) | `v1_fix` | 1,245 | 1,250 | 1,014 | 11,433 | $0.13 |
| **Total** | | | | | | **$0.13** |

Prices: $2 / 1M input, $10 / 1M output incl. thinking.
"""


def test_results_snapshot_supplies_scores_and_costs(client):
    box_repair_run(server.RUNS_DIR)
    server.RESULTS_DIR.joinpath("tier_A.md").write_text(SNAPSHOT.format(digest=server.compare_hash()))
    (snap,) = client.get("/api/results").json()
    assert (snap["path"], snap["harness"], snap["prices"]) == \
        ("results/tier_A.md", "f53f81f", "$2 / 1M input, $10 / 1M output incl. thinking.")
    assert snap["calls"] == [{"step": "Repair 1: circular import hrloop <-> metext (`__init__.py`)",
                              "interaction_id": "v1_fix", "packet_tokens": 1245,
                              "billed_input_tokens": 1250, "output_tokens": 1014,
                              "thought_tokens": 11433, "cost_usd": 0.13}]
    (run,) = client.get("/api/runs").json()
    assert run["cost_usd"] == 0.13 and run["cost_complete"]

    data = client.get("/api/test-results").json()
    assert data["source"] == "results/tier_A.md" and data["hash_matches"]
    hold = data["results"]["testpm10_stack2"]
    assert (hold["passes"], hold["role"], hold["slope_ols"], hold["zero_agreement"],
            hold["p99_rel_err"], hold["h4h_fails"]) == (True, "holdout", 0.99999, 0.995, 2e-5, "0/36")
    by_name = {c["name"]: c for c in client.get("/api/certify").json()["criteria"]}
    assert not by_name["suite_found"]["ok"] and "results/tier_A.md" in by_name["suite_found"]["detail"]

    server.RESULTS_DIR.joinpath("tier_A.md").write_text(SNAPSHOT.format(digest="0" * 64))
    assert client.get("/api/test-results").json()["hash_matches"] is False
