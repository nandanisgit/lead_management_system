"""MessagingChannel port — WhatsApp and Telegram (research R16, R17).

No templates and no business-initiated messages (FR-022): every send is a reply.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """A tutee message (or Business-app echo) in channel-neutral form."""

    id: str  # channel message ID (dedupe key)
    contact: str  # channel address: E.164 number (WhatsApp) or "tg:<chat id>" (Telegram)
    type: Literal["text", "interactive", "contact", "unsupported"]
    text: str | None = None
    choice_id: str | None = None  # id of a tapped button / list row
    profile_name: str | None = None
    referral_source: str | None = None  # click-to-WhatsApp campaign id
    timestamp: datetime
    is_echo: bool = False  # sent by a human from the Business app (coexistence)
    shared_phone: str | None = None  # a phone number shared with the app's contact button


class Choice(BaseModel):
    """A tap option (button or list row): ``id`` comes back when tapped."""

    id: str
    title: str


class OutboundMessage(BaseModel):
    """A reply: text plus optional tap options.

    ``list_button`` / ``list_section`` are the labels a channel shows when the options are
    rendered as a list (WhatsApp: the button that opens it and the section title); they are
    user-facing copy, so the engine fills them from config/messages.yaml.
    """

    text: str
    choices: list[Choice] = Field(default_factory=list)
    list_button: str | None = None
    list_section: str | None = None
    # FR-032: label of the one-tap "share my phone number" control; channels that have one
    # show it (Telegram), others ignore it
    phone_request_label: str | None = None


class SentMessage(BaseModel):
    """The channel's ID for a sent message (stored in the transcript)."""

    id: str


class Capabilities(BaseModel):
    """What a channel supports, so the engine never assumes WhatsApp."""

    max_buttons: int
    max_list_rows: int
    has_service_window: bool
    window_hours: float
    contact_is_phone: bool = False  # the channel address is the tutee's phone number
    can_request_phone: bool = False  # the channel has a "share my phone number" control


class ChannelError(Exception):
    """Send failed after retries."""


class SignatureError(Exception):
    """Inbound request failed authenticity check."""


@runtime_checkable
class MessagingChannel(Protocol):
    """A messaging app as the engine needs it (research R16)."""

    name: str
    path_name: str  # URL segment: /webhooks/{path_name}
    capabilities: Capabilities

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """Return the challenge to echo back, or None if verification fails."""

    def parse_inbound(self, headers: Mapping[str, str], body: bytes) -> list[InboundMessage]:
        """Verify authenticity (raise SignatureError) and normalise the payload."""

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        """Send a reply to ``to``; return the channel's message ID."""
        ...


def as_numbered_text(message: OutboundMessage) -> OutboundMessage:
    """Fallback for channels without buttons/lists: choices become numbered lines."""
    if not message.choices:
        return message
    lines = [message.text, ""] + [f"{i}. {c.title}" for i, c in enumerate(message.choices, 1)]
    return OutboundMessage(text="\n".join(lines))


def fit_to_capabilities(message: OutboundMessage, caps: Capabilities) -> OutboundMessage:
    """Degrade choices to numbered text when there are more than the channel can show."""
    limit = max(caps.max_buttons, caps.max_list_rows)
    if message.choices and len(message.choices) > limit:
        return as_numbered_text(message)
    return message
