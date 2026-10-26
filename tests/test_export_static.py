"""tools/export_static.py: the static site certifies only what CI scored on the committed port."""

from __future__ import annotations

import json

import pytest

import export_static
import server


def snapshot_with(tmp_path, monkeypatch, **changes):
    snap = json.loads(export_static.SNAPSHOT.read_text())
    port = changes.pop("port_sha256", None)
    if port:
        snap["suite"]["port_sha256"] = port
        for r in snap["suite"]["results"]:
            r["port_sha256"] = port
    snap.update(changes)
    path = tmp_path / "ci_port_suite.json"
    path.write_text(json.dumps(snap))
    monkeypatch.setattr(export_static, "SNAPSHOT", path)


def test_site_has_every_response_the_ui_fetches():
    out_dir = server.OUT_DIR
    files, _ = export_static.build()
    assert server.OUT_DIR == out_dir
    runs = json.loads(files["data/runs.json"])
    config = json.loads(files["data/whatif/config.json"])
    wanted = {"overview", "frozen", "runs", "results", "tokens", "test-results", "provenance",
              "certify", "commits", "whatif/config"}
    wanted |= {f"runs/{r['id']}" for r in runs}
    wanted |= {f"whatif/{p}/{f}" for p in config["pollutants"] for f in config["fuel_mix"]}
    assert {f"data/{name}.json" for name in wanted} <= files.keys()
    index = files["index.html"]
    assert index.index('src="data/static.js"') < index.index('src="app.js"')


def test_certified_only_when_ci_scored_the_committed_port(tmp_path, monkeypatch):
    snapshot_with(tmp_path, monkeypatch, port_sha256="0" * 64)
    files, meta = export_static.build()
    assert not meta["port_matches"] and not meta["certified"]
    assert meta["label"].startswith("Not certified") and "000000000000" in meta["label"]
    certify = json.loads(files["data/certify.json"])
    assert not certify["certified"]
    assert "scored_this_port" in {c["name"] for c in certify["criteria"] if not c["ok"]}
    assert json.loads(files["data/overview.json"])["certified_tiers"] == []


def test_no_snapshot_is_not_certified(tmp_path, monkeypatch):
    monkeypatch.setattr(export_static, "SNAPSHOT", tmp_path / "missing.json")
    files, meta = export_static.build()
    assert meta["ci"] is None and not meta["certified"]
    assert meta["label"] == f"Not certified: no CI snapshot ({export_static.SNAPSHOT_NAME})"
    assert not json.loads(files["data/certify.json"])["certified"]


def test_refuses_to_export_a_secret(tmp_path, monkeypatch):
    snapshot_with(tmp_path, monkeypatch, run_url="https://example.invalid/AIza" + "x" * 35)
    with pytest.raises(SystemExit, match="secret"):
        export_static.build()
