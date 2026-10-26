"""agent/argon.py request bodies and polling, against a fake Interactions client."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import argon


class FakeInteractions:
    def __init__(self, statuses, text="=== FILE: aermod_py/a.py ===\nA = 1\n"):
        self.statuses = list(statuses)
        self.text = text
        self.created, self.polled = [], 0

    def _interaction(self):
        status = self.statuses.pop(0)
        return SimpleNamespace(id="int-1", status=status,
                               output_text=self.text if status == "completed" else None,
                               usage=SimpleNamespace(model_dump=lambda **k: {"total_tokens": 42}),
                               errors=None if status != "failed" else [{"message": "boom"}])

    def create(self, **body):
        self.created.append(body)
        return self._interaction()

    def get(self, id):
        assert id == "int-1"
        self.polled += 1
        return self._interaction()


def client(statuses, **kw):
    return SimpleNamespace(interactions=FakeInteractions(statuses, **kw))


def test_model_request_polls_background_interaction_until_done():
    c = client(["queued", "in_progress", "completed"])
    reply = argon.ask(c, input="hi", system_instruction="sys", thinking_level="high",
                      max_output_tokens=1000, poll_seconds=0)
    body = c.interactions.created[0]
    assert body["model"] == "gemini-4-argon" and body["background"] and body["store"]
    assert body["generation_config"] == {"thinking_level": "high", "max_output_tokens": 1000}
    assert "agent" not in body
    assert c.interactions.polled == 2
    assert reply.status == "completed" and reply.usage == {"total_tokens": 42}
    assert reply.text.startswith("=== FILE")


def test_agent_request_uses_antigravity_config():
    c = client(["completed"])
    argon.ask(c, input="hi", system_instruction="sys", agent=True, max_total_tokens=5_000_000)
    body = c.interactions.created[0]
    assert body["agent"] == argon.ANTIGRAVITY_AGENT
    assert body["agent_config"] == {"type": "antigravity", "model": "gemini-4-argon",
                                    "max_total_tokens": 5_000_000}
    assert "model" not in body and "generation_config" not in body


def test_failed_interaction_raises_with_the_reply_attached(tmp_path):
    c = client(["in_progress", "failed"])
    with pytest.raises(argon.ArgonError) as exc:
        argon.ask(c, input="hi", system_instruction="sys", poll_seconds=0)
    assert exc.value.reply.status == "failed"
    exc.value.reply.save(tmp_path)
    assert (tmp_path / "reply.json").exists()


def test_unknown_thinking_level_is_refused():
    with pytest.raises(ValueError):
        argon.ask(client(["completed"]), input="", system_instruction="", thinking_level="max")


def test_client_needs_an_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(argon.ArgonError, match="GEMINI_API_KEY"):
        argon.make_client()
