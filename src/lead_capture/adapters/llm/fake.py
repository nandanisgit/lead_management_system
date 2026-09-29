"""FakeLLMClient — scripted results for tests; records every call."""

from __future__ import annotations

from collections.abc import Callable
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
    def __init__(
        self,
        extractions: list[ExtractionScript] | None = None,
        replies: list[ReplyScript] | None = None,
        *,
        timeout: bool = False,
        default_reply: Callable[[TurnContext, Instruction], str] | None = None,
    ) -> None:
        self._extractions = list(extractions or [])
        self._replies = list(replies or [])
        self._timeout = timeout
        self._default_reply = default_reply or (lambda t, i: f"[{i.kind}] {i.params}")
        self.calls: list[tuple[str, Any]] = []

    def queue_extraction(self, result: ExtractionScript) -> None:
        self._extractions.append(result)

    async def extract(self, turn: TurnContext) -> ExtractionResult:
        self.calls.append(("extract", turn))
        if self._timeout:
            raise LLMTimeout("fake timeout")
        script = self._extractions.pop(0) if self._extractions else ExtractionResult()
        result = script(turn) if callable(script) else script
        result = result.model_copy(update={"usage": TokenUsage(model="fake", input_tokens=1)})
        return result.only_known_fields()

    async def write_reply(self, turn: TurnContext, instruction: Instruction) -> ReplyResult:
        self.calls.append(("write_reply", instruction))
        if self._timeout:
            raise LLMTimeout("fake timeout")
        script = self._replies.pop(0) if self._replies else self._default_reply
        text = script(turn, instruction) if callable(script) else script
        return ReplyResult(text=text, usage=TokenUsage(model="fake", output_tokens=1))
