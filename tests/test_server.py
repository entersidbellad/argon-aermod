"""server.py: read-only endpoints over agent/runs, out/suite_*.json and split provenance."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import server
import split


@pytest.fixture
def client(tmp_path, monkeypatch):
    runs, out, port = tmp_path / "runs", tmp_path / "out", tmp_path / "aermod_py"
    for d in (runs, out, port):
        d.mkdir()
    (port / "README.md").write_text("readme\n")
    monkeypatch.setattr(server, "RUNS_DIR", runs)
    monkeypatch.setattr(server, "OUT_DIR", out)
    monkeypatch.setattr(server, "PORT_DIR", port)
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
    assert len(detail["reply_details"]) == 2 and detail["run"]["model"] == "m"


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
    assert data["results"]["CAPPED_STACK2"] == {"passes": True, "epa_pass": True,
                                                "strict_pass": True, "error": None}
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
