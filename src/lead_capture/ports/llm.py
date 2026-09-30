"""LLMClient port — the only way the engine reaches a language model (research R16).

Why: the model vendor can change (another Claude route, another provider) without touching
the engine. Field names are not listed here: the fields the model may propose come from
config/requirement.yaml and are handed to adapters when they are built.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Tokens used by one model call — recorded per conversation for cost tracking (R15)."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Signals(BaseModel):
    """Conversation signals the model reports alongside extracted fields.

    These drive engine behaviour (consent, handoff, off-topic, minors…), so they are part of
    the code contract rather than config.
    """

    language: Literal["en", "hi", "other"] = "en"
    consent: Literal["given", "declined", "none"] = "none"
    confirms_summary: bool | None = None
    wants_human: bool = False
    not_interested: bool = False
    accepts_online: bool | None = None
    new_student: bool = False
    deletion_request: bool = False
    complaint_or_sensitive: bool = False
    understood: bool = True
    likely_minor_alone: bool = False
    off_topic: bool = False
    asks_fees_or_tutors: bool = False


class ExtractionResult(BaseModel):
    """What the model proposes for one turn. A proposal only — the engine validates it."""

    fields: dict[str, Any] = Field(default_factory=dict)
    signals: Signals = Field(default_factory=Signals)
    usage: TokenUsage | None = None

    def only_known_fields(self, allowed: Collection[str]) -> ExtractionResult:
        """Drop fields the schema doesn't define (and empty values) before validation."""
        known = {k: v for k, v in self.fields.items() if k in allowed and v is not None}
        return self.model_copy(update={"fields": known})


class TranscriptLine(BaseModel):
    """One message of the recent transcript given to the model."""

    role: Literal["tutee", "assistant"]
    text: str


class TurnContext(BaseModel):
    """What the engine gives the model for one turn. Built by code, trimmed to settings."""

    transcript: list[TranscriptLine] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)  # validated values only
    missing: list[str] = Field(default_factory=list)
    language: Literal["en", "hi"] = "en"
    stage: str = "in_progress"


class Instruction(BaseModel):
    """What code decided this turn's reply must do; the model only phrases it."""

    kind: str  # e.g. ASK, SUMMARISE_AND_CONFIRM, CLOSE_COMPLETED, HANDOFF_ACK ...
    params: dict[str, Any] = Field(default_factory=dict)
    strict: bool = False  # FR-029: no small talk


class ReplyResult(BaseModel):
    """A model-written reply (checked by the guards before sending)."""

    text: str
    usage: TokenUsage | None = None


class LLMError(Exception):
    """Model call failed after retries."""


class LLMTimeout(LLMError):
    """Model call exceeded llm.timeout_seconds."""


@runtime_checkable
class LLMClient(Protocol):
    """A language model as the engine needs it: extraction and reply phrasing."""

    async def extract(self, turn: TurnContext) -> ExtractionResult:
        """Propose field values and signals from the recent conversation."""
        ...

    async def write_reply(self, turn: TurnContext, instruction: Instruction) -> ReplyResult:
        """Phrase the reply the engine decided on (``instruction``) — nothing more."""
        ...
