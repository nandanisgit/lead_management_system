"""OllamaLLMClient passes the shared LLM contract and builds requests from settings only."""

import json

import httpx
import pytest
import respx

from lead_capture.adapters.llm import prompting
from lead_capture.adapters.llm.ollama import OllamaLLMClient
from lead_capture.domain.schema import get_schema
from lead_capture.ports.llm import (
    Instruction,
    LLMError,
    TranscriptLine,
    TurnContext,
)
from lead_capture.registry import build_llm
from lead_capture.settings import Secrets, load_settings
from tests.contract.llm_client_suite import ALL_CHECKS

BASE = "http://ollama.test:11434"
URL = f"{BASE}/api/chat"


def _answer(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "message": {"role": "assistant", "content": content},
            "prompt_eval_count": 850,
            "eval_count": 40,
        },
    )


def _extraction(fields: dict) -> str:
    return json.dumps({"fields": fields, "signals": {"language": "en", "understood": True}})


def _responder(fields: dict):
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "format" in body:
            return _answer(_extraction(fields))
        return _answer("Which board is he in?")

    return handle


def settings(**ollama):
    return load_settings(
        llm={"provider": "ollama", "max_retries": 0, "ollama": {"base_url": BASE, **ollama}}
    )


def client(s=None, **ollama):
    s = s or settings(**ollama)
    return OllamaLLMClient(
        s.llm,
        fields_schema=get_schema().llm_fields_schema(),
        max_questions=s.conversation.max_questions_per_message,
        max_words=s.conversation.max_words_per_message,
    )


def factory(scenario):
    if scenario == "timeout":
        respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    elif scenario == "extra_fields":
        respx.post(URL).mock(side_effect=_responder({"grade_level": "Class 9", "junk": 1}))
    else:
        respx.post(URL).mock(side_effect=_responder({"grade_level": "Class 9"}))
    return client()


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
@respx.mock
async def test_llm_client_suite(check):
    await check(factory)


TURN = TurnContext(
    transcript=[TranscriptLine(role="tutee", text=f"msg {i}") for i in range(10)],
    state={"note": "x"},
    missing=["grade_level"],
)


@respx.mock
async def test_extraction_request_comes_from_settings():
    route = respx.post(URL).mock(side_effect=_responder({"grade_level": "Class 9", "junk": 1}))
    s = settings(extraction_model="tiny:1b", context_window=4096, temperature={"extraction": 0.1})
    s = s.model_copy(update={"llm": s.llm.model_copy(update={"context_messages": 3})})
    result = await client(s).extract(TURN)
    body = json.loads(route.calls.last.request.content)
    schema = get_schema()
    assert body["model"] == "tiny:1b" and body["stream"] is False
    assert body["format"] == prompting.response_schema(schema.llm_fields_schema())
    assert body["options"] == {"num_predict": 400, "num_ctx": 4096, "temperature": 0.1}
    assert body["keep_alive"] == "30m"
    system, user = body["messages"]
    assert system["role"] == "system" and '"fields"' in system["content"]
    assert "record_requirements tool" not in system["content"]
    assert "msg 9" in user["content"] and "msg 6" not in user["content"]  # trimmed to 3
    assert result.fields == {"grade_level": "Class 9"}  # junk dropped
    assert result.usage.model == "tiny:1b" and result.usage.input_tokens == 850


@respx.mock
async def test_reply_request_has_no_format_and_uses_reply_model():
    route = respx.post(URL).mock(side_effect=_responder({}))
    turn = TurnContext(transcript=[TranscriptLine(role="tutee", text="hi")], language="hi")
    reply = await client(reply_model="chat:7b").write_reply(
        turn, Instruction(kind="ASK", params={"fields": ["board"]}, strict=True)
    )
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "chat:7b" and "format" not in body
    assert body["options"]["num_predict"] == 200 and body["options"]["temperature"] == 0.7
    assert "Hindi" in body["messages"][1]["content"]
    assert reply.text == "Which board is he in?" and reply.usage.output_tokens == 40


@respx.mock
async def test_json_wrapped_in_prose_is_accepted():
    respx.post(URL).mock(
        return_value=_answer("Here you go:\n```json\n" + _extraction({"mode": "home"}) + "\n```")
    )
    result = await client().extract(TURN)
    assert result.fields == {"mode": "home"}


@respx.mock
async def test_non_json_answer_is_an_llm_error():
    respx.post(URL).mock(return_value=_answer("sorry, I can't"))
    with pytest.raises(LLMError):
        await client().extract(TURN)


@respx.mock
async def test_missing_model_is_an_llm_error():
    respx.post(URL).mock(return_value=httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMError, match="404"):
        await client().extract(TURN)


@respx.mock
async def test_server_errors_are_retried_up_to_max_retries():
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(503), httpx.ConnectError("down"), _answer(_extraction({}))]
    )
    s = settings()
    s = s.model_copy(update={"llm": s.llm.model_copy(update={"max_retries": 2})})
    await client(s).extract(TURN)
    assert route.call_count == 3


@respx.mock
async def test_gives_up_after_max_retries():
    respx.post(URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(LLMError):
        await client().extract(TURN)


def test_concurrency_cap_comes_from_settings():
    assert client(max_concurrent_calls=3)._sem._value == 3


def test_registry_builds_ollama_client():
    llm = build_llm(settings(), Secrets(_env_file=None), get_schema())
    assert isinstance(llm, OllamaLLMClient)


def test_extraction_prompt_is_a_compact_field_guide_not_the_schema():
    from lead_capture.domain.schema import get_schema

    schema = get_schema()
    system = client()._extract_system
    for name in schema.field_names():
        assert f"- {name}:" in system
    assert "one of: online, home, either" in system
    assert '"additionalProperties"' not in system  # the JSON schema itself is not pasted
