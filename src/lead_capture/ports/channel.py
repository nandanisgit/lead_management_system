"""MessagingChannel port — WhatsApp today, other channels later (research R16).

No templates and no business-initiated messages (FR-022): every send is a reply.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    id: str  # channel message ID (dedupe key)
    contact: str  # E.164 number or channel user ID
    type: Literal["text", "interactive", "unsupported"]
    text: str | None = None
    choice_id: str | None = None  # id of a tapped button / list row
    profile_name: str | None = None
    referral_source: str | None = None  # click-to-WhatsApp campaign id
    timestamp: datetime
    is_echo: bool = False  # sent by a human from the Business app (coexistence)


class Choice(BaseModel):
    id: str
    title: str


class OutboundMessage(BaseModel):
    text: str
    choices: list[Choice] = Field(default_factory=list)


class SentMessage(BaseModel):
    id: str


class Capabilities(BaseModel):
    max_buttons: int
    max_list_rows: int
    has_service_window: bool
    window_hours: float


class ChannelError(Exception):
    """Send failed after retries."""


class SignatureError(Exception):
    """Inbound request failed authenticity check."""


@runtime_checkable
class MessagingChannel(Protocol):
    name: str
    capabilities: Capabilities

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """Return the challenge to echo back, or None if verification fails."""

    def parse_inbound(self, headers: Mapping[str, str], body: bytes) -> list[InboundMessage]:
        """Verify authenticity (raise SignatureError) and normalise the payload."""

    async def send(self, to: str, message: OutboundMessage) -> SentMessage: ...


def as_numbered_text(message: OutboundMessage) -> OutboundMessage:
    """Fallback for channels without buttons/lists: choices become numbered lines."""
    if not message.choices:
        return message
    lines = [message.text, ""] + [f"{i}. {c.title}" for i, c in enumerate(message.choices, 1)]
    return OutboundMessage(text="\n".join(lines))


def fit_to_capabilities(message: OutboundMessage, caps: Capabilities) -> OutboundMessage:
    limit = max(caps.max_buttons, caps.max_list_rows)
    if message.choices and len(message.choices) > limit:
        return as_numbered_text(message)
    return message
