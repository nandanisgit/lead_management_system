"""Shared contract suite for every LLMClient adapter (fake, stub, anthropic, future providers).

``factory(scenario)`` returns a client for a scenario: "normal", "extra_fields", "timeout".
"""

from __future__ import annotations

import pytest

from lead_capture.ports.llm import (
    EXTRACTABLE_FIELDS,
    ExtractionResult,
    Instruction,
    LLMClient,
    LLMTimeout,
    ReplyResult,
    TranscriptLine,
    TurnContext,
)

TURN = TurnContext(
    transcript=[TranscriptLine(role="tutee", text="Class 9 CBSE maths, home tuition in Dwarka")],
    missing=["grade_level", "board", "subjects", "mode"],
)


async def check_is_llm_client(factory):
    assert isinstance(factory("normal"), LLMClient)


async def check_extract_returns_result_with_usage(factory):
    result = await factory("normal").extract(TURN)
    assert isinstance(result, ExtractionResult)
    assert result.usage is not None and result.usage.model


async def check_extract_drops_unknown_fields(factory):
    result = await factory("extra_fields").extract(TURN)
    assert set(result.fields) <= set(EXTRACTABLE_FIELDS)


async def check_reply_returns_text_with_usage(factory):
    reply = await factory("normal").write_reply(
        TURN, Instruction(kind="ASK", params={"fields": ["mode"]})
    )
    assert isinstance(reply, ReplyResult) and reply.text.strip()
    assert reply.usage is not None


async def check_timeout_raises_typed_error(factory):
    client = factory("timeout")
    with pytest.raises(LLMTimeout):
        await client.extract(TURN)


ALL_CHECKS = [
    check_is_llm_client,
    check_extract_returns_result_with_usage,
    check_extract_drops_unknown_fields,
    check_reply_returns_text_with_usage,
    check_timeout_raises_typed_error,
]
