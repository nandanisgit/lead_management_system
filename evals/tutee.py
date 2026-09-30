"""Simulated tutee for evals (research R10).

Why: scripted tutee lines break whenever the bot asks in a different order. A small model
(Claude, or a free local Ollama model) plays the tutee instead, answering only from the
scenario's facts in its style. Evals are test tooling, not domain code, so calling the vendor
API here is allowed (the CLAUDE.md adapter rule applies to src/).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx

SYSTEM = """You are role-playing a person on WhatsApp who wants a tutor. You are chatting with a
tutoring service's assistant.

Your true facts (never contradict them, never invent others):
{facts}

Your style: {style}
{extra}
Rules:
- Answer only what the assistant asks, using only your facts. If asked something not in your
  facts, say you're not sure.
- Keep replies short, like real WhatsApp messages.
- If the assistant shows options with ids like [#mode:home], you may tap one by replying with
  exactly the id, e.g. #mode:home. Otherwise reply in text.
- When the assistant shows a summary that matches your facts, confirm it.
- Output only your next message."""


class OllamaTuteeClient:
    """Minimal stand-in for ``anthropic.Anthropic`` that sends the tutee's turns to Ollama.

    Why: lets evals run for free on a local model. It exposes ``messages.create`` with the
    same arguments and response shape the tutee already uses, so ``SimulatedTutee`` doesn't
    change. URL, timeout and context size come from ``llm.ollama`` in settings.
    """

    def __init__(self, base_url: str, timeout_seconds: float, context_window: int, client=None):
        """Remember where Ollama listens; ``client`` is injectable for tests."""
        self._http = client or httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self._num_ctx = context_window
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, *, model, max_tokens, system, messages):
        """Call ``/api/chat`` and return an Anthropic-shaped response (text blocks + usage)."""
        resp = self._http.post(
            "/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [{"role": "system", "content": system}, *messages],
                "options": {"num_predict": max_tokens, "num_ctx": self._num_ctx},
            },
        )
        resp.raise_for_status()
        body = resp.json()
        text = (body.get("message") or {}).get("content") or ""
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=body.get("prompt_eval_count") or 0,
                output_tokens=body.get("eval_count") or 0,
            ),
        )


class SimulatedTutee:
    """A model playing the tutee, constrained to the scenario's facts."""

    def __init__(
        self, model: str, max_tokens: int, facts: dict, style: str, extra: str = "", client=None
    ):
        """Prepare the role-play prompt; ``client`` defaults to the Anthropic SDK."""
        self._client = client or anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self._system = SYSTEM.format(
            facts=json.dumps(facts, ensure_ascii=False, indent=1), style=style, extra=extra
        )
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def reply(self, transcript: list[tuple[str, str]]) -> str:
        """transcript: [(role, text)] with role "assistant" (the bot) or "tutee"."""
        messages = []
        for role, text in transcript:
            # from the simulator's point of view the bot is the "user"
            messages.append(
                {"role": "user" if role == "assistant" else "assistant", "content": text}
            )
        if not messages or messages[0]["role"] != "user":
            messages.insert(0, {"role": "user", "content": "(conversation start)"})
        resp = self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens, system=self._system, messages=messages
        )
        self.usage["input_tokens"] += resp.usage.input_tokens
        self.usage["output_tokens"] += resp.usage.output_tokens
        return "".join(b.text for b in resp.content if b.type == "text").strip()
