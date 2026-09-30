"""OllamaLLMClient — LLMClient adapter for a local Ollama server (research R2, R16).

Why: lets the service run on free, locally hosted open models while it is being tried out,
with the same prompts, schema and validation as the Claude adapter. Extraction uses Ollama's
structured output (``format`` = the JSON schema from ``prompting.response_schema``) instead
of a tool call. Every model name, URL, timeout, concurrency cap, context size and temperature
comes from ``llm.ollama`` in config/settings.yaml. The engine never imports this module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

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

CHAT_PATH = "/api/chat"


def _json_object(text: str) -> dict[str, Any]:
    """Parse the model's answer as one JSON object.

    Structured output normally returns bare JSON; the outermost ``{…}`` is tried as a fallback
    in case a model wraps it in prose or code fences. Anything else is an LLMError, which the
    engine treats as "not understood" (the tutee is asked to rephrase).
    """
    for candidate in (text, text[text.find("{") : text.rfind("}") + 1]):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise LLMError("invalid_json")


def _usage(model: str, body: dict[str, Any]) -> TokenUsage:
    """Token counts reported by Ollama (free, but still recorded to compare with Claude)."""
    return TokenUsage(
        model=model,
        input_tokens=body.get("prompt_eval_count") or 0,
        output_tokens=body.get("eval_count") or 0,
    )


class OllamaLLMClient:
    """LLMClient on Ollama's ``/api/chat`` endpoint."""

    def __init__(
        self,
        settings: LLMSettings,
        *,
        fields_schema: dict[str, Any],
        max_questions: int,
        max_words: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Build from settings.

        ``fields_schema`` comes from RequirementSchema; the question/word limits come from
        conversation settings and fill the reply prompt. ``client`` is injectable for tests.
        """
        self._s = settings
        self._o = settings.ollama
        self._client = client or httpx.AsyncClient(
            base_url=self._o.base_url, timeout=self._o.timeout_seconds
        )
        self._sem = asyncio.Semaphore(self._o.max_concurrent_calls)
        self._schema = prompting.response_schema(fields_schema)
        self._known = set(fields_schema["properties"])
        self._extract_system = prompting.extraction_system(
            "extraction_output_json.md",
            field_guide=prompting.field_guide(fields_schema),
            signal_names=", ".join(prompting.SIGNAL_SCHEMA),
        )
        self._reply_system = prompting.reply_system(max_questions, max_words)

    def _request(
        self, model: str, system: str, content: str, max_tokens: int, temperature: float
    ) -> dict[str, Any]:
        """The ``/api/chat`` body shared by extraction and replies (non-streaming)."""
        return {
            "model": model,
            "stream": False,
            "keep_alive": self._o.keep_alive,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "options": {
                "num_predict": max_tokens,
                "num_ctx": self._o.context_window,
                "temperature": temperature,
            },
        }

    async def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST one chat request under the concurrency cap and map failures to port errors.

        Connection errors and 5xx answers are retried up to ``llm.max_retries`` times;
        timeouts are not retried (a slow local model would only be slower the second time).
        """
        async with self._sem:
            for attempt in range(self._s.max_retries + 1):
                last = attempt == self._s.max_retries
                try:
                    resp = await self._client.post(CHAT_PATH, json=body)
                except httpx.TimeoutException as exc:
                    raise LLMTimeout("model call timed out") from exc
                except httpx.TransportError as exc:
                    if last:
                        raise LLMError(type(exc).__name__) from exc
                    continue
                if resp.status_code >= 500 and not last:
                    continue
                if resp.status_code == 404:
                    log.error("ollama_model_missing", extra={"model": body["model"]})
                if resp.status_code >= 400:
                    raise LLMError(f"ollama_http_{resp.status_code}")
                return resp.json()
        raise LLMError("unreachable")  # pragma: no cover - loop always returns or raises

    async def extract(self, turn: TurnContext) -> ExtractionResult:
        """Structured-output call constrained to the response schema; unknown fields dropped."""
        model = self._o.extraction_model
        body = self._request(
            model,
            self._extract_system,
            prompting.extraction_content(turn, self._s.context_messages),
            self._s.max_output_tokens.extraction,
            self._o.temperature.extraction,
        )
        body["format"] = self._schema
        answer = await self._call(body)
        payload = _json_object((answer.get("message") or {}).get("content") or "")
        return prompting.parse_extraction(payload, self._known, _usage(model, answer))

    async def write_reply(self, turn: TurnContext, instruction: Instruction) -> ReplyResult:
        """Plain-text reply from the reply model, following the engine's instruction."""
        model = self._o.reply_model
        answer = await self._call(
            self._request(
                model,
                self._reply_system,
                prompting.reply_content(turn, instruction, self._s.context_messages),
                self._s.max_output_tokens.reply,
                self._o.temperature.reply,
            )
        )
        text = ((answer.get("message") or {}).get("content") or "").strip()
        return ReplyResult(text=text, usage=_usage(model, answer))
