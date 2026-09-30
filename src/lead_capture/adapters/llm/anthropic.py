"""AnthropicLLMClient — LLMClient adapter for the Claude API (contracts/llm-extraction.md).

All models, token limits, context size, timeouts, retries and concurrency come
from ``LLMSettings`` (config/settings.yaml). Prompts and schemas are shared with the other
providers (``prompting``). The engine never imports this module.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic

from lead_capture.adapters.llm import prompting
from lead_capture.ports.llm import (
    ExtractionResult,
    Instruction,
    LLMError,
    LLMTimeout,
    ReplyResult,
    TokenUsage,
    TurnContext,
)
from lead_capture.settings import LLMSettings

log = logging.getLogger(__name__)

TOOL_NAME = "record_requirements"
TOOL_DESCRIPTION = (
    "Record every tutoring requirement detail found in the tutee's latest message(s), plus "
    "conversation signals. Include only details the tutee actually stated; never infer budget "
    "or schedule. Omit fields not mentioned. Follow each field's description."
)


def build_tool(fields_schema: dict[str, Any]) -> dict[str, Any]:
    """The forced extraction tool: fields from config/requirement.yaml, signals from code."""
    return {
        "name": TOOL_NAME,
        "description": TOOL_DESCRIPTION,
        "input_schema": prompting.response_schema(fields_schema),
    }


def _usage(model: str, usage: Any) -> TokenUsage:
    """Token counts from the API response, for cost tracking."""
    return TokenUsage(
        model=model,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )


class AnthropicLLMClient:
    """LLMClient on the Claude API."""

    def __init__(
        self,
        settings: LLMSettings,
        api_key: str | None,
        *,
        fields_schema: dict[str, Any],
        max_questions: int,
        max_words: int,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        """Build from settings.

        ``fields_schema`` comes from RequirementSchema; the question/word limits come from
        conversation settings and fill the system prompt.
        """
        self._s = settings
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=settings.timeout_seconds, max_retries=settings.max_retries
        )
        self._sem = asyncio.Semaphore(settings.max_concurrent_calls)
        self._tool = build_tool(fields_schema)
        self._known = set(fields_schema["properties"])
        self._extract_system = prompting.extraction_system("extraction_output_tool.md")
        self._reply_system = prompting.reply_system(max_questions, max_words)

    def _system(self, text: str) -> list[dict[str, Any]]:
        """System prompt block, marked for prompt caching when enabled (cost saving)."""
        block: dict[str, Any] = {"type": "text", "text": text}
        if self._s.prompt_cache:
            block["cache_control"] = {"type": "ephemeral"}
        return [block]

    def _tools(self) -> list[dict[str, Any]]:
        """The extraction tool, marked for prompt caching when enabled."""
        tool = dict(self._tool)
        if self._s.prompt_cache:
            tool["cache_control"] = {"type": "ephemeral"}
        return [tool]

    async def _call(self, **kwargs: Any) -> Any:
        """One API call under the concurrency cap, with SDK errors mapped to port errors."""
        async with self._sem:
            try:
                return await self._client.messages.create(**kwargs)
            except anthropic.APITimeoutError as exc:
                raise LLMTimeout("model call timed out") from exc
            except anthropic.APIError as exc:
                raise LLMError(type(exc).__name__) from exc

    async def extract(self, turn: TurnContext) -> ExtractionResult:
        """Forced tool call on the extraction model; unknown fields are dropped."""
        model = self._s.extraction_model
        resp = await self._call(
            model=model,
            max_tokens=self._s.max_output_tokens.extraction,
            system=self._system(self._extract_system),
            tools=self._tools(),
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": prompting.extraction_content(turn, self._s.context_messages),
                }
            ],
        )
        payload: dict[str, Any] = {}
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                payload = dict(block.input or {})
                break
        return prompting.parse_extraction(payload, self._known, _usage(model, resp.usage))

    async def write_reply(self, turn: TurnContext, instruction: Instruction) -> ReplyResult:
        """Plain-text reply from the reply model, following the engine's instruction."""
        model = self._s.reply_model
        resp = await self._call(
            model=model,
            max_tokens=self._s.max_output_tokens.reply,
            system=self._system(self._reply_system),
            messages=[
                {
                    "role": "user",
                    "content": prompting.reply_content(turn, instruction, self._s.context_messages),
                }
            ],
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        return ReplyResult(text=text, usage=_usage(model, resp.usage))
