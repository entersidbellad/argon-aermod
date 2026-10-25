"""Gemini 4 Argon through the google-genai Interactions API (google-genai >= 2.3.0).

One function, ``ask``, used by the one-pass port, the repair loop and the
chunked baseline. Interactions are created with ``background=True`` and
``store=True`` and polled with ``interactions.get`` until they leave the
queued/in-progress states, so a long full-context generation does not depend
on one HTTP request staying open. Every reply is saved with its usage.

``agent=True`` runs the request through the Antigravity agent instead of the
bare model. That path is built from the SDK's types
(``AntigravityAgentConfigParam``) but has never been run against the service.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from google import genai

MODEL = "gemini-4-argon"
ANTIGRAVITY_AGENT = "antigravity-preview-05-2026"
THINKING_LEVELS = ("minimal", "low", "medium", "high")
PENDING = {"queued", "in_progress"}


class ArgonError(RuntimeError):
    def __init__(self, message: str, reply: "Reply | None" = None) -> None:
        super().__init__(message)
        self.reply = reply


@dataclass
class Reply:
    id: str
    status: str
    text: str
    seconds: float
    usage: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def save(self, run_dir: Path, stem: str = "reply") -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / f"{stem}.txt").write_text(self.text)
        meta = asdict(self)
        del meta["text"]
        (run_dir / f"{stem}.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")


def make_client() -> genai.Client:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise ArgonError("set GEMINI_API_KEY to call Gemini 4 Argon")
    return genai.Client()


def _dump(obj) -> dict | list:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    return obj


def ask(client, *, input: str, system_instruction: str, thinking_level: str = "high",
        max_output_tokens: int | None = None, temperature: float | None = None,
        previous_interaction_id: str | None = None, agent: bool = False,
        max_total_tokens: int | None = None, poll_seconds: float = 15.0,
        timeout_seconds: float = 6 * 3600.0) -> Reply:
    """Create one interaction, wait for it to finish, and return its text."""
    if thinking_level not in THINKING_LEVELS:
        raise ValueError(f"thinking_level must be one of {THINKING_LEVELS}")
    body: dict = {"input": input, "system_instruction": system_instruction,
                  "background": True, "store": True}
    if previous_interaction_id:
        body["previous_interaction_id"] = previous_interaction_id
    if agent:
        config = {"type": "antigravity", "model": MODEL}
        if max_total_tokens:
            config["max_total_tokens"] = max_total_tokens
        body.update(agent=ANTIGRAVITY_AGENT, agent_config=config)
    else:
        gen: dict = {"thinking_level": thinking_level}
        if max_output_tokens:
            gen["max_output_tokens"] = max_output_tokens
        if temperature is not None:
            gen["temperature"] = temperature
        body.update(model=MODEL, generation_config=gen)

    t0 = time.monotonic()
    interaction = client.interactions.create(**body)
    while interaction.status in PENDING:
        if time.monotonic() - t0 > timeout_seconds:
            raise ArgonError(f"interaction {interaction.id} still {interaction.status} "
                             f"after {timeout_seconds:.0f}s")
        time.sleep(poll_seconds)
        interaction = client.interactions.get(id=interaction.id)
    reply = Reply(id=interaction.id, status=str(interaction.status),
                  text=interaction.output_text or "", seconds=time.monotonic() - t0,
                  usage=_dump(interaction.usage), errors=_dump(interaction.errors or []))
    if reply.status != "completed":
        raise ArgonError(f"interaction {reply.id} ended {reply.status}: {reply.errors}", reply)
    return reply
