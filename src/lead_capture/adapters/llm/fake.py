"""FakeLLMClient — scripted model results for tests and the `chat` CLI; records every call.

Why: engine and integration tests must be deterministic and free, so they script what the
"model" returns instead of calling a real one.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Any

from lead_capture.ports.llm import (
    ExtractionResult,
    Instruction,
    LLMTimeout,
    ReplyResult,
    TokenUsage,
    TurnContext,
)

ExtractionScript = ExtractionResult | Callable[[TurnContext], ExtractionResult]
ReplyScript = str | Callable[[TurnContext, Instruction], str]


class FakeLLMClient:
    """LLMClient returning queued extraction/reply scripts (see the contract suite)."""

    def __init__(
        self,
        extractions: list[ExtractionScript] | None = None,
        replies: list[ReplyScript] | None = None,
        *,
        timeout: bool = False,
        default_reply: Callable[[TurnContext, Instruction], str] | None = None,
        known_fields: Collection[str] | None = None,
    ) -> None:
        """Queue scripted results; ``known_fields`` defaults to the configured schema."""
        self._extractions = list(extractions or [])
        self._replies = list(replies or [])
        self._timeout = timeout
        self._default_reply = default_reply or (lambda t, i: f"[{i.kind}] {i.params}")
        self.calls: list[tuple[str, Any]] = []
        if known_fields is None:
            from lead_capture.domain.schema import get_schema

            known_fields = get_schema().field_names()
        self._known = set(known_fields)

    def queue_extraction(self, result: ExtractionScript) -> None:
        """Add the result the next ``extract`` call returns."""
        self._extractions.append(result)

    async def extract(self, turn: TurnContext) -> ExtractionResult:
        """Return the next queued extraction (empty when none), minus unknown fields."""
        self.calls.append(("extract", turn))
        if self._timeout:
            raise LLMTimeout("fake timeout")
        script = self._extractions.pop(0) if self._extractions else ExtractionResult()
        result = script(turn) if callable(script) else script
        result = result.model_copy(update={"usage": TokenUsage(model="fake", input_tokens=1)})
        return result.only_known_fields(self._known)

    async def write_reply(self, turn: TurnContext, instruction: Instruction) -> ReplyResult:
        """Return the next queued reply, or the default reply for the instruction."""
        self.calls.append(("write_reply", instruction))
        if self._timeout:
            raise LLMTimeout("fake timeout")
        script = self._replies.pop(0) if self._replies else self._default_reply
        text = script(turn, instruction) if callable(script) else script
        return ReplyResult(text=text, usage=TokenUsage(model="fake", output_tokens=1))
