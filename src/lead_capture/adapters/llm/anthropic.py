"""AnthropicLLMClient — LLMClient adapter for the Claude API (contracts/llm-extraction.md).

All models, token limits, context size, timeouts, retries and concurrency come
from ``LLMSettings`` (config/settings.yaml). The engine never imports this module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import anthropic

from lead_capture.ports.llm import (
    ExtractionResult,
    Instruction,
    LLMError,
    LLMTimeout,
    ReplyResult,
    Signals,
    TokenUsage,
    TurnContext,
)
from lead_capture.settings import ROOT, LLMSettings

log = logging.getLogger(__name__)
PROMPTS = ROOT / "prompts"

_SIGNAL_SCHEMA: dict[str, dict[str, Any]] = {
    "language": {"type": "string", "enum": ["en", "hi", "other"]},
    "consent": {"type": "string", "enum": ["given", "declined", "none"]},
    "confirms_summary": {"type": "boolean"},
    "wants_human": {"type": "boolean"},
    "not_interested": {"type": "boolean"},
    "accepts_online": {"type": "boolean"},
    "new_student": {
        "type": "boolean",
        "description": "Tutee is starting a requirement for a different student",
    },
    "deletion_request": {"type": "boolean"},
    "complaint_or_sensitive": {"type": "boolean"},
    "understood": {
        "type": "boolean",
        "description": "False if the message could not be understood",
    },
    "likely_minor_alone": {
        "type": "boolean",
        "description": "The person chatting appears to be under 18 and no parent is involved",
    },
    "off_topic": {
        "type": "boolean",
        "description": "The message is not about the tutoring requirement",
    },
    "asks_fees_or_tutors": {
        "type": "boolean",
        "description": "The tutee asks about fees, rates, tutor names or availability",
    },
}

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
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": fields_schema,
                "signals": {
                    "type": "object",
                    "properties": _SIGNAL_SCHEMA,
                    "required": ["language", "understood"],
                    "additionalProperties": False,
                },
            },
            "required": ["fields", "signals"],
        },
    }


def _transcript(turn: TurnContext, limit: int) -> str:
    """The last ``limit`` messages as plain lines (context size is a cost setting)."""
    lines = turn.transcript[-limit:]
    return "\n".join(f"{'Tutee' if ln.role == 'tutee' else 'Assistant'}: {ln.text}" for ln in lines)


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
        self._extract_system = (PROMPTS / "extraction.md").read_text()
        self._reply_system = (
            (PROMPTS / "assistant.md")
            .read_text()
            .replace("{max_questions}", str(max_questions))
            .replace("{max_words}", str(max_words))
        )

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
        content = (
            f"Captured so far (validated): {json.dumps(turn.state, ensure_ascii=False)}\n"
            f"Still missing: {', '.join(turn.missing) or 'nothing'}\n"
            f"Conversation stage: {turn.stage}\n\n"
            f"Recent messages (oldest first):\n{_transcript(turn, self._s.context_messages)}"
        )
        resp = await self._call(
            model=model,
            max_tokens=self._s.max_output_tokens.extraction,
            system=self._system(self._extract_system),
            tools=self._tools(),
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": content}],
        )
        payload: dict[str, Any] = {}
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                payload = dict(block.input or {})
                break
        try:
            signals = Signals.model_validate(payload.get("signals") or {})
        except ValueError:
            signals = Signals()
        result = ExtractionResult(
            fields=payload.get("fields") or {}, signals=signals, usage=_usage(model, resp.usage)
        )
        return result.only_known_fields(self._known)

    async def write_reply(self, turn: TurnContext, instruction: Instruction) -> ReplyResult:
        """Plain-text reply from the reply model, following the engine's instruction."""
        model = self._s.reply_model
        language = "Hindi/Hinglish (Roman script)" if turn.language == "hi" else "English"
        content = (
            f"Captured details: {json.dumps(turn.state, ensure_ascii=False)}\n"
            f"Still missing: {', '.join(turn.missing) or 'nothing'}\n"
            f"Reply language: {language}\n"
            f"Strict mode: {'yes' if instruction.strict else 'no'}\n\n"
            f"Recent messages (oldest first):\n{_transcript(turn, self._s.context_messages)}\n\n"
            f"Instruction: {instruction.kind} {json.dumps(instruction.params, ensure_ascii=False)}"
        )
        resp = await self._call(
            model=model,
            max_tokens=self._s.max_output_tokens.reply,
            system=self._system(self._reply_system),
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        return ReplyResult(text=text, usage=_usage(model, resp.usage))
