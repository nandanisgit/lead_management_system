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
    name = "fake"

    def __init__(
        self, capabilities: Capabilities | None = None, verify_token: str = "fake"
    ) -> None:
        self.capabilities = capabilities or Capabilities(
            max_buttons=3, max_list_rows=10, has_service_window=True, window_hours=24
        )
        self._verify_token = verify_token
        self.sent: list[tuple[str, OutboundMessage]] = []
        self._ids = itertools.count(1)

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        if params.get("hub.verify_token") == self._verify_token:
            return params.get("hub.challenge", "")
        return None

    def make_payload(self, messages: list[dict], valid: bool = True) -> tuple[dict, bytes]:
        body = json.dumps(messages).encode()
        sig = hmac.new(_SECRET, body, hashlib.sha256).hexdigest() if valid else "bad"
        return {"x-fake-signature": sig}, body

    def parse_inbound(self, headers: Mapping[str, str], body: bytes) -> list[InboundMessage]:
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
                )
            )
        return out

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        self.sent.append((to, message))
        return SentMessage(id=f"fake-out-{next(self._ids)}")

    def texts_to(self, to: str) -> list[str]:
        return [m.text for t, m in self.sent if t == to]
