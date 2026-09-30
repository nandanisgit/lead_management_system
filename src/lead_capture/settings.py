"""Validated settings: config/settings.yaml, overridable by LC__GROUP__KEY env vars.

Constitution Principle VI / research R16: every performance and cost number lives here.
Secrets are read separately (``Secrets``) from plain environment variables.
"""

from __future__ import annotations

import os
from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, PositiveFloat, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_FILE = ROOT / "config" / "settings.yaml"


class _Tokens(BaseModel):
    """Output-token caps per call type."""

    extraction: PositiveInt
    reply: PositiveInt


class SchemaFiles(BaseModel):
    """Paths (relative to the project root) of the config that defines fields and texts."""

    requirement_file: str
    messages_file: str


class _Temperatures(BaseModel):
    """Sampling temperature per call type (providers that accept one)."""

    extraction: float = Field(ge=0, le=2)
    reply: float = Field(ge=0, le=2)


class OllamaSettings(BaseModel):
    """Local Ollama server used as a free model during development (research R2, R16).

    Local models are slower than the Claude API and serve few requests at once, so they
    get their own models, timeout, concurrency and context size instead of sharing Claude's.
    """

    base_url: str
    extraction_model: str
    reply_model: str
    timeout_seconds: PositiveFloat
    max_concurrent_calls: PositiveInt
    context_window: PositiveInt
    temperature: _Temperatures
    keep_alive: str


class LLMSettings(BaseModel):
    """Model choice and cost/performance knobs per call (research R16).

    ``extraction_model``/``reply_model``/``timeout_seconds``/``max_concurrent_calls`` at the
    top level are for the Claude API; the ``ollama`` group has its own.
    """

    provider: Literal["anthropic", "ollama", "fake", "stub"]
    extraction_model: str
    reply_model: str
    combined_call: bool
    context_messages: PositiveInt
    max_output_tokens: _Tokens
    prompt_cache: bool
    timeout_seconds: PositiveFloat
    max_retries: int = Field(ge=0)
    max_concurrent_calls: PositiveInt
    skip_for_deterministic_turns: bool
    max_regenerations: int = Field(ge=0)
    require_grounding: bool
    stub_delay_seconds: tuple[float, float]
    ollama: OllamaSettings


class ConversationSettings(BaseModel):
    """Conversation limits and thresholds (FR-001, FR-019, FR-023, FR-030)."""

    max_questions_per_message: PositiveInt
    max_words_per_message: PositiveInt
    debounce_ms: int = Field(ge=0)
    misunderstand_handoff_threshold: PositiveInt
    stalled_after_hours: PositiveFloat
    handoff_expiry_hours: PositiveFloat
    max_turns_per_contact_per_hour: PositiveInt
    max_turns_per_contact_per_day: PositiveInt
    off_topic_max_sentences: PositiveInt
    short_answer_max_words: int = Field(ge=0)


class TelegramSettings(BaseModel):
    """Telegram Bot API address and keyboard layout (research R17)."""

    api_base_url: str
    buttons_per_row: PositiveInt


class ChannelSettings(BaseModel):
    """Messaging adapter choice, send timeout and retries."""

    provider: Literal["whatsapp_cloud", "telegram", "fake"]
    send_timeout_seconds: PositiveFloat
    max_retries: int = Field(ge=0)
    retry_backoff_seconds: float = Field(ge=0)
    telegram: TelegramSettings


class LeadsSettings(BaseModel):
    """Lead-register adapter choice, outbox timing and API timeout."""

    repository: Literal["google_sheet", "in_memory"]
    outbox_interval_seconds: PositiveInt
    max_backoff_seconds: PositiveInt
    retry_base_seconds: PositiveFloat
    request_timeout_seconds: PositiveFloat


class ProviderSettings(BaseModel):
    """Which adapter to use for a simple port (queue, lock, clock)."""

    provider: str


class OpsSettings(BaseModel):
    """Operations team time zone and working hours."""

    timezone: str
    hours_start: time
    hours_end: time

    @model_validator(mode="after")
    def _order(self) -> OpsSettings:
        """Working hours must start before they end."""
        if self.hours_start >= self.hours_end:
            raise ValueError("ops.hours_start must be before ops.hours_end")
        return self


class RetentionSettings(BaseModel):
    """How long each kind of data is kept (FR-026)."""

    transcript_days: PositiveInt
    lead_days: PositiveInt
    handoff_days: PositiveInt
    usage_days: PositiveInt


class JobsSettings(BaseModel):
    """How often scheduled jobs run."""

    stalled_every_minutes: PositiveInt
    handoff_sync_every_minutes: PositiveInt
    retention_cron: str


class CostsSettings(BaseModel):
    """Where price rates live and the currency conversion for reports."""

    rates_file: str
    usd_to_inr: PositiveFloat


class EvalsSettings(BaseModel):
    """Eval runs: repeats, pass threshold, tutee model, PR subset."""

    repeats: PositiveInt
    pass_threshold: float = Field(gt=0, le=1)
    tutee_model: str
    ollama_tutee_model: str
    pr_subset: list[str]
    max_turns: PositiveInt
    tutee_max_tokens: PositiveInt
    simulated_time: time


class _Burst(BaseModel):
    """The `burst` load profile (real model, test sheet)."""

    concurrent_tutees: PositiveInt
    peak_msgs_per_second: PositiveFloat
    minutes: PositiveFloat


class _Capacity(BaseModel):
    """The `capacity` load profile (stubbed model)."""

    max_tutees: PositiveInt


class _Soak(BaseModel):
    """The `soak` load profile (stubbed model, hours of steady traffic)."""

    msgs_per_second: PositiveFloat
    hours: PositiveFloat


class LoadSettings(BaseModel):
    """Load-test profile parameters (research R13)."""

    burst: _Burst
    capacity: _Capacity
    soak: _Soak


class Settings(BaseSettings):
    """Every tunable number in one validated object (config/settings.yaml + LC__ env)."""

    model_config = SettingsConfigDict(env_prefix="LC__", env_nested_delimiter="__", extra="forbid")

    schema_files: SchemaFiles
    llm: LLMSettings
    conversation: ConversationSettings
    channel: ChannelSettings
    leads: LeadsSettings
    queue: ProviderSettings
    lock: ProviderSettings
    clock: ProviderSettings
    ops: OpsSettings
    retention: RetentionSettings
    jobs: JobsSettings
    costs: CostsSettings
    evals: EvalsSettings
    load: LoadSettings

    def effective(self) -> dict[str, Any]:
        """Plain dict of the settings in force — printed in eval and load reports."""
        return self.model_dump(mode="json")


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge nested dicts: values in ``override`` win, nested groups merge."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _env_overrides() -> dict:
    """LC__GROUP__KEY environment variables as a nested dict."""
    tree: dict = {}
    for name, value in os.environ.items():
        if not name.startswith("LC__"):
            continue
        parts = [p.lower() for p in name[4:].split("__") if p]
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return tree


def load_settings(path: Path | str | None = None, **overrides: Any) -> Settings:
    """Load YAML defaults, apply LC__ env overrides, then keyword overrides; validate."""
    file = Path(path or os.environ.get("LC_SETTINGS_FILE") or DEFAULT_SETTINGS_FILE)
    data = yaml.safe_load(file.read_text()) or {}
    data = _deep_merge(data, _env_overrides())
    data = _deep_merge(data, overrides)
    return Settings.model_validate(data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings for this process, loaded once."""
    return load_settings()


class Secrets(BaseSettings):
    """Secrets from plain environment variables (never in YAML or code)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str | None = None
    wa_phone_number_id: str | None = None
    wa_access_token: str | None = None
    wa_app_secret: str | None = None
    wa_verify_token: str | None = None
    wa_api_version: str = "v23.0"
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    lead_sheet_id: str | None = None
    google_service_account_file: str | None = None
    load_test_sheet_id: str | None = None
    database_url: str = "sqlite:///data/lead_capture.db"
