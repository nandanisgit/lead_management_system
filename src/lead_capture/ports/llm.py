"""LLMClient port — the only way the engine reaches a language model (research R16)."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

# Field names the extraction may propose (contracts/llm-extraction.md). Anything else is dropped.
EXTRACTABLE_FIELDS: tuple[str, ...] = (
    "contact_name",
    "relationship",
    "student_name",
    "grade_level",
    "board",
    "subjects",
    "mode",
    "area",
    "city",
    "pincode",
    "schedule",
    "start_date",
    "budget_min",
    "budget_max",
    "budget_unit",
    "goal",
    "sessions_per_week",
    "tutor_preferences",
    "level_notes",
    "email",
    "guardian_name",
    "guardian_relationship",
)


class TokenUsage(BaseModel):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Signals(BaseModel):
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
    fields: dict[str, Any] = Field(default_factory=dict)
    signals: Signals = Field(default_factory=Signals)
    usage: TokenUsage | None = None

    def only_known_fields(self) -> ExtractionResult:
        known = {k: v for k, v in self.fields.items() if k in EXTRACTABLE_FIELDS and v is not None}
        return self.model_copy(update={"fields": known})


class TranscriptLine(BaseModel):
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
    text: str
    usage: TokenUsage | None = None


class LLMError(Exception):
    """Model call failed after retries."""


class LLMTimeout(LLMError):
    """Model call exceeded llm.timeout_seconds."""


@runtime_checkable
class LLMClient(Protocol):
    async def extract(self, turn: TurnContext) -> ExtractionResult: ...

    async def write_reply(self, turn: TurnContext, instruction: Instruction) -> ReplyResult: ...
