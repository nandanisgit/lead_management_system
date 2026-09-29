import pytest

from lead_capture.settings import Settings, load_settings


def test_defaults_load_from_yaml():
    s = load_settings()
    assert s.llm.reply_model == "claude-sonnet-5-5"
    assert s.llm.context_messages == 6
    assert s.conversation.max_questions_per_message == 2
    assert s.ops.timezone == "Asia/Kolkata"
    assert s.retention.transcript_days == 90


def test_env_overrides_nested_keys(monkeypatch):
    monkeypatch.setenv("LC__LLM__REPLY_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("LC__CONVERSATION__DEBOUNCE_MS", "500")
    s = load_settings()
    assert s.llm.reply_model == "claude-haiku-4-5"
    assert s.conversation.debounce_ms == 500


@pytest.mark.parametrize(
    "env,value",
    [
        ("LC__LLM__TIMEOUT_SECONDS", "-1"),
        ("LC__LLM__CONTEXT_MESSAGES", "0"),
        ("LC__LLM__PROVIDER", "nonsense"),
        ("LC__OPS__HOURS_START", "18:00"),
    ],
)
def test_invalid_values_raise(monkeypatch, env, value):
    monkeypatch.setenv(env, value)
    with pytest.raises(ValueError):
        load_settings()


def test_effective_returns_plain_dict():
    eff = load_settings().effective()
    assert eff["llm"]["extraction_model"] == "claude-haiku-4-5"
    assert isinstance(Settings.model_fields, dict)
