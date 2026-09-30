"""Evals can run for free on Ollama: provider choice and the Ollama-backed simulated tutee."""

import json

import httpx
import respx
from evals.runner import _eval_settings, _tutee_model_and_client
from evals.tutee import OllamaTuteeClient, SimulatedTutee


def test_provider_defaults_to_settings_and_model_goes_to_that_provider(monkeypatch):
    monkeypatch.setenv("LC__LLM__PROVIDER", "ollama")
    s = _eval_settings(None, "big:27b")
    assert s.llm.provider == "ollama" and s.llm.ollama.reply_model == "big:27b"
    s = _eval_settings("anthropic", "claude-x")
    assert s.llm.provider == "anthropic" and s.llm.reply_model == "claude-x"


def test_fake_provider_falls_back_to_a_real_model(monkeypatch):
    monkeypatch.setenv("LC__LLM__PROVIDER", "fake")
    assert _eval_settings(None, None).llm.provider == "anthropic"


def test_tutee_uses_ollama_model_when_bot_does():
    s = _eval_settings("ollama", None)
    model, client = _tutee_model_and_client(s)
    assert model == s.evals.ollama_tutee_model and isinstance(client, OllamaTuteeClient)
    assert _tutee_model_and_client(_eval_settings("anthropic", None))[1] is None


@respx.mock
def test_ollama_tutee_replies_from_facts():
    route = respx.post("http://ollama.test/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"content": " Class 9 \n"},
                "prompt_eval_count": 90,
                "eval_count": 3,
            },
        )
    )
    client = OllamaTuteeClient("http://ollama.test", 5, 2048)
    tutee = SimulatedTutee("tiny:1b", 150, {"class": "9"}, "short", client=client)
    assert tutee.reply([("assistant", "Which class?")]) == "Class 9"
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "tiny:1b" and body["options"] == {"num_predict": 150, "num_ctx": 2048}
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1] == {"role": "user", "content": "Which class?"}
    assert tutee.usage == {"input_tokens": 90, "output_tokens": 3}
