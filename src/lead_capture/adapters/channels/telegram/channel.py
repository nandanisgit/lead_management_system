"""TelegramChannel — MessagingChannel adapter for the Telegram Bot API (research R17).

Why: lets tutees reach the same conversation engine and lead register from Telegram, which
needs no business verification. Everything Telegram-specific (secret-token check, update
parsing, keyboards, webhook registration) stays in this package.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping

from lead_capture.adapters.channels.telegram import parser
from lead_capture.adapters.channels.telegram.sender import TelegramSender
from lead_capture.ports.channel import (
    Capabilities,
    InboundMessage,
    OutboundMessage,
    SentMessage,
    SignatureError,
    fit_to_capabilities,
)
from lead_capture.settings import ChannelSettings, Secrets

SECRET_HEADER = "x-telegram-bot-api-secret-token"
# Telegram platform limit: an inline keyboard holds at most 100 buttons.
MAX_INLINE_BUTTONS = 100
ALLOWED_UPDATES = ["message", "callback_query"]


class TelegramChannel:
    """MessagingChannel for a Telegram bot (replies only; no service window)."""

    name = "telegram"
    path_name = "telegram"  # webhook URL registered with Telegram: /webhooks/telegram

    def __init__(self, settings: ChannelSettings, secrets: Secrets) -> None:
        """Build from channel settings and the bot token / webhook secret."""
        self._secret = secrets.telegram_webhook_secret
        self._sender = TelegramSender(settings, secrets.telegram_bot_token)
        self._taps: dict[str, list[str]] = {}  # address → button taps to acknowledge
        self.capabilities = Capabilities(
            max_buttons=MAX_INLINE_BUTTONS,
            max_list_rows=MAX_INLINE_BUTTONS,
            has_service_window=False,
            window_hours=0,
            contact_is_phone=False,  # Telegram never reveals the user's number by itself
            can_request_phone=True,  # …but has a one-tap "share my phone number" button
        )

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """Telegram has no GET handshake; the webhook is registered with ``register_webhook``."""
        return None

    def parse_inbound(self, headers: Mapping[str, str], body: bytes) -> list[InboundMessage]:
        """Reject requests without our secret token, then normalise the update."""
        lowered = {k.lower(): v for k, v in headers.items()}
        if not self._secret:
            raise SignatureError("TELEGRAM_WEBHOOK_SECRET not configured")
        if not hmac.compare_digest(lowered.get(SECRET_HEADER, ""), self._secret):
            raise SignatureError("bad secret token")
        messages, taps = parser.parse(body)
        for tap in taps:
            self._taps.setdefault(tap.address, []).append(tap.callback_id)
        return messages

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        """Acknowledge pending button taps for this chat, then send the reply."""
        for callback_id in self._taps.pop(to, []):
            await self._sender.answer_tap(callback_id)
        return await self._sender.send(to, fit_to_capabilities(message, self.capabilities))

    async def register_webhook(self, public_url: str) -> None:
        """Point Telegram at ``<public_url>/webhooks/telegram`` with our secret token."""
        if not self._secret:
            raise SignatureError("TELEGRAM_WEBHOOK_SECRET not configured")
        await self._sender.call(
            "setWebhook",
            {
                "url": f"{public_url.rstrip('/')}/webhooks/{self.path_name}",
                "secret_token": self._secret,
                "allowed_updates": ALLOWED_UPDATES,
            },
        )
