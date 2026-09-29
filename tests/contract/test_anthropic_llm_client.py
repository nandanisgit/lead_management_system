from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from lead_capture.adapters.llm.anthropic import TOOL, AnthropicLLMClient
from lead_capture.ports.llm import (
    EXTRACTABLE_FIELDS,
    Instruction,
    Signals,
    TranscriptLine,
    TurnContext,
)
from lead_capture.settings import load_settings
from tests.contract.llm_client_suite import ALL_CHECKS

USAGE = SimpleNamespace(
    input_tokens=120, output_tokens=30, cache_read_input_tokens=900, cache_creation_input_tokens=0
)


class FakeSDK:
    """Stands in for anthropic.AsyncAnthropic (the SDK uses httpx2, which respx can't patch)."""

    def __init__(self, timeout=False):
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)
        self._timeout = timeout

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._timeout:
            raise anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api"))
        if kwargs.get("tools"):
            block = SimpleNamespace(
                type="tool_use",
                input={
                    "fields": {"grade_level": "Class 9", "junk": 1},
                    "signals": {"language": "en", "understood": True},
                },
            )
        else:
            block = SimpleNamespace(type="text", text="Which board is he in?")
        return SimpleNamespace(content=[block], usage=USAGE)


def client(sdk=None, **llm):
    s = load_settings(llm={"max_retries": 0, **llm})
    return AnthropicLLMClient(s.llm, api_key="test-key", client=sdk or FakeSDK())


def factory(scenario):
    return client(FakeSDK(timeout=scenario == "timeout"))


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
async def test_llm_client_suite(check):
    await check(factory)


def test_tool_schema_matches_contract():
    props = TOOL["input_schema"]["properties"]
    assert set(props["fields"]["properties"]) == set(EXTRACTABLE_FIELDS)
    assert set(props["signals"]["properties"]) == set(Signals.model_fields)
    assert TOOL["name"] == "record_requirements"


async def test_extraction_request_uses_settings():
    sdk = FakeSDK()
    turn = TurnContext(
        transcript=[TranscriptLine(role="tutee", text=f"msg {i}") for i in range(10)],
        state={"contact_name": "Priya"},
        missing=["grade_level"],
    )
    result = await client(sdk, context_messages=3).extract(turn)
    body = sdk.calls[-1]
    assert body["model"] == "claude-haiku-4-5"
    assert body["max_tokens"] == 400 and "temperature" not in body
    assert body["tool_choice"] == {"type": "tool", "name": "record_requirements"}
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["tools"][0]["cache_control"] == {"type": "ephemeral"}
    user = body["messages"][0]["content"]
    assert "msg 9" in user and "msg 7" in user and "msg 6" not in user  # trimmed to 3
    assert result.fields == {"grade_level": "Class 9"}  # junk dropped
    assert result.usage.cache_read_tokens == 900 and result.usage.input_tokens == 120


async def test_reply_request_uses_reply_model_and_no_tools():
    sdk = FakeSDK()
    turn = TurnContext(transcript=[TranscriptLine(role="tutee", text="hi")], language="hi")
    reply = await client(sdk, prompt_cache=False).write_reply(
        turn, Instruction(kind="ASK", params={"fields": ["board"]}, strict=True)
    )
    body = sdk.calls[-1]
    assert body["model"] == "claude-sonnet-5-5" and "tools" not in body
    assert body["max_tokens"] == 200 and "cache_control" not in body["system"][0]
    content = body["messages"][0]["content"]
    assert "Hindi" in content and "Strict mode: yes" in content
    assert reply.text == "Which board is he in?"


async def test_concurrency_cap_comes_from_settings():
    c = client(max_concurrent_calls=7)
    assert c._sem._value == 7
