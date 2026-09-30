"""Telegram Bot API sender: sendMessage with inline buttons or a share-phone keyboard.

Why: turns the engine's channel-neutral OutboundMessage into Bot API calls. The bot token is
part of every URL, so it must never be logged (logging.py silences HTTP client request logs).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx

from lead_capture.adapters.channels.telegram.parser import chat_id
from lead_capture.ports.channel import (
    ChannelError,
    OutboundMessage,
    SentMessage,
    as_numbered_text,
)
from lead_capture.settings import ChannelSettings

log = logging.getLogger(__name__)
# Telegram platform limits (not tunables): callback data is at most 64 bytes.
CALLBACK_DATA_MAX_BYTES = 64
RETRYABLE = 429


def _rows(items: list, per_row: int) -> list[list]:
    """Split buttons into keyboard rows."""
    return [items[i : i + per_row] for i in range(0, len(items), per_row)]


def build_payload(to: str, message: OutboundMessage, buttons_per_row: int) -> dict:
    """``sendMessage`` body: plain text plus inline buttons, a share-phone key, or neither.

    Choices whose IDs don't fit Telegram's callback data fall back to numbered text. A plain
    reply removes any earlier share-phone keyboard.
    """
    if message.choices and any(
        len(c.id.encode()) > CALLBACK_DATA_MAX_BYTES for c in message.choices
    ):
        message = as_numbered_text(message)
    payload: dict = {"chat_id": chat_id(to), "text": message.text}
    if message.choices:
        buttons = [{"text": c.title, "callback_data": c.id} for c in message.choices]
        payload["reply_markup"] = {"inline_keyboard": _rows(buttons, buttons_per_row)}
    elif message.phone_request_label:
        payload["reply_markup"] = {
            "keyboard": [[{"text": message.phone_request_label, "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True,
        }
    else:
        payload["reply_markup"] = {"remove_keyboard": True}
    return payload


class TelegramSender:
    """Calls the Bot API with the timeout, retries and backoff from channel settings."""

    def __init__(self, settings: ChannelSettings, token: str | None) -> None:
        """Base URL from settings; the token from secrets (never logged)."""
        self._s = settings
        self._base = f"{settings.telegram.api_base_url.rstrip('/')}/bot{token}"

    async def call(self, method: str, body: dict) -> dict:
        """POST one Bot API method; retry 429/5xx and network errors, never other 4xx."""
        attempts = self._s.max_retries + 1
        error = "unknown"
        async with httpx.AsyncClient(timeout=self._s.send_timeout_seconds) as client:
            for attempt in range(attempts):
                try:
                    resp = await client.post(f"{self._base}/{method}", json=body)
                except httpx.HTTPError as exc:
                    error = type(exc).__name__
                else:
                    if resp.status_code < 300 and resp.json().get("ok"):
                        return resp.json().get("result") or {}
                    error = f"http_{resp.status_code}"
                    if resp.status_code != RETRYABLE and resp.status_code < 500:
                        break  # e.g. 403: the user blocked the bot — not retried
                if attempt < attempts - 1:
                    await asyncio.sleep(self._s.retry_backoff_seconds * 2**attempt)
        log.warning("telegram_call_failed", extra={"method": method, "error": error})
        raise ChannelError(error)

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        """Send one reply; returns ``tg-out-<chat id>-<message_id>``."""
        payload = build_payload(to, message, self._s.telegram.buttons_per_row)
        result = await self.call("sendMessage", payload)
        return SentMessage(id=f"tg-out-{payload['chat_id']}-{result.get('message_id')}")

    async def answer_tap(self, callback_id: str) -> None:
        """Stop the button's loading spinner; failures don't matter to the conversation."""
        with contextlib.suppress(ChannelError):
            await self.call("answerCallbackQuery", {"callback_query_id": callback_id})
