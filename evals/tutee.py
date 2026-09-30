"""Simulated tutee for evals (research R10).

Why: scripted tutee lines break whenever the bot asks in a different order. A small Claude
model plays the tutee instead, answering only from the scenario's facts in its style. Evals
are test tooling, not domain code, so calling the vendor SDK here is allowed (the CLAUDE.md
adapter rule applies to src/).
"""

from __future__ import annotations

import json

import anthropic

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
