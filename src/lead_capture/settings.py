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
    extraction: PositiveInt
    reply: PositiveInt


class _Temps(BaseModel):
    extraction: float = Field(ge=0, le=1)
    reply: float = Field(ge=0, le=1)


class LLMSettings(BaseModel):
    provider: Literal["anthropic", "fake", "stub"]
    extraction_model: str
    reply_model: str
    combined_call: bool
    context_messages: PositiveInt
    max_output_tokens: _Tokens
    temperature: _Temps
    prompt_cache: bool
    timeout_seconds: PositiveFloat
    max_retries: int = Field(ge=0)
    max_concurrent_calls: PositiveInt
    skip_for_deterministic_turns: bool
    max_regenerations: int = Field(ge=0)
    stub_delay_seconds: tuple[float, float]


class ConversationSettings(BaseModel):
    max_questions_per_message: PositiveInt
    max_words_per_message: PositiveInt
    debounce_ms: int = Field(ge=0)
    misunderstand_handoff_threshold: PositiveInt
    stalled_after_hours: PositiveFloat
    handoff_expiry_hours: PositiveFloat
    max_turns_per_contact_per_hour: PositiveInt
    max_turns_per_contact_per_day: PositiveInt
    off_topic_max_sentences: PositiveInt


class ChannelSettings(BaseModel):
    provider: Literal["whatsapp_cloud", "fake"]
    send_timeout_seconds: PositiveFloat
    max_retries: int = Field(ge=0)


class LeadsSettings(BaseModel):
    repository: Literal["google_sheet", "in_memory"]
    outbox_interval_seconds: PositiveInt
    max_backoff_seconds: PositiveInt


class ProviderSettings(BaseModel):
    provider: str


class OpsSettings(BaseModel):
    timezone: str
    hours_start: time
    hours_end: time

    @model_validator(mode="after")
    def _order(self) -> OpsSettings:
        if self.hours_start >= self.hours_end:
            raise ValueError("ops.hours_start must be before ops.hours_end")
        return self


class RetentionSettings(BaseModel):
    transcript_days: PositiveInt
    lead_days: PositiveInt
    handoff_days: PositiveInt
    usage_days: PositiveInt


class JobsSettings(BaseModel):
    stalled_every_minutes: PositiveInt
    handoff_sync_every_minutes: PositiveInt
    retention_cron: str


class CostsSettings(BaseModel):
    rates_file: str
    usd_to_inr: PositiveFloat


class EvalsSettings(BaseModel):
    repeats: PositiveInt
    pass_threshold: float = Field(gt=0, le=1)
    tutee_model: str
    pr_subset: list[str]


class _Burst(BaseModel):
    concurrent_tutees: PositiveInt
    peak_msgs_per_second: PositiveFloat
    minutes: PositiveFloat


class _Capacity(BaseModel):
    max_tutees: PositiveInt


class _Soak(BaseModel):
    msgs_per_second: PositiveFloat
    hours: PositiveFloat


class LoadSettings(BaseModel):
    burst: _Burst
    capacity: _Capacity
    soak: _Soak


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LC__", env_nested_delimiter="__", extra="forbid")

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
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _env_overrides() -> dict:
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
    lead_sheet_id: str | None = None
    google_service_account_file: str | None = None
    load_test_sheet_id: str | None = None
    database_url: str = "sqlite:///data/lead_capture.db"
