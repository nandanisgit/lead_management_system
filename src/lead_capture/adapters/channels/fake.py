"""FakeChannel — in-memory channel for tests and `lead-capture chat`."""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from lead_capture.ports.channel import (
    Capabilities,
    InboundMessage,
    OutboundMessage,
    SentMessage,
    SignatureError,
)

_SECRET = b"fake-secret"


class FakeChannel:
    """MessagingChannel kept in memory: tests and `lead-capture chat` read what was sent."""

    name = "fake"
    path_name = "fake"

    def __init__(
        self, capabilities: Capabilities | None = None, verify_token: str = "fake"
    ) -> None:
        """Default capabilities match WhatsApp (3 buttons, 10 list rows, 24-hour window)."""
        self.capabilities = capabilities or Capabilities(
            max_buttons=3,
            max_list_rows=10,
            has_service_window=True,
            window_hours=24,
            contact_is_phone=True,
        )
        self._verify_token = verify_token
        self.sent: list[tuple[str, OutboundMessage]] = []
        self._ids = itertools.count(1)

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """Accept the fake verify token, like the real webhook check."""
        if params.get("hub.verify_token") == self._verify_token:
            return params.get("hub.challenge", "")
        return None

    def make_payload(self, messages: list[dict], valid: bool = True) -> tuple[dict, bytes]:
        """Build a signed (or deliberately badly signed) inbound payload for tests."""
        body = json.dumps(messages).encode()
        sig = hmac.new(_SECRET, body, hashlib.sha256).hexdigest() if valid else "bad"
        return {"x-fake-signature": sig}, body

    def parse_inbound(self, headers: Mapping[str, str], body: bytes) -> list[InboundMessage]:
        """Check the fake signature and turn the payload into InboundMessages."""
        expected = hmac.new(_SECRET, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(headers.get("x-fake-signature", ""), expected):
            raise SignatureError("bad fake signature")
        out = []
        for m in json.loads(body):
            out.append(
                InboundMessage(
                    id=m["id"],
                    contact=m["contact"],
                    type=m.get("type", "interactive" if m.get("choice_id") else "text"),
                    text=m.get("text"),
                    choice_id=m.get("choice_id"),
                    profile_name=m.get("profile_name"),
                    referral_source=m.get("referral_source"),
                    timestamp=m.get("timestamp") or datetime.now(UTC),
                    is_echo=m.get("is_echo", False),
                    shared_phone=m.get("shared_phone"),
                )
            )
        return out

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        """Record the message instead of sending it; returns a fake message ID."""
        self.sent.append((to, message))
        return SentMessage(id=f"fake-out-{next(self._ids)}")

    def texts_to(self, to: str) -> list[str]:
        """Texts sent to one contact, in order (test helper)."""
        return [m.text for t, m in self.sent if t == to]
