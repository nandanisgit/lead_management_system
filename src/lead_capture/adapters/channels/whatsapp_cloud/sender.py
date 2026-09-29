"""WhatsApp Cloud API sender: text, reply buttons (≤3), interactive list (≤10). No templates."""

from __future__ import annotations

import asyncio
import logging

import httpx

from lead_capture.ports.channel import ChannelError, OutboundMessage, SentMessage
from lead_capture.settings import ChannelSettings, Secrets

log = logging.getLogger(__name__)
BUTTON_TITLE_MAX = 20
ROW_TITLE_MAX = 24
MAX_BUTTONS = 3
MAX_ROWS = 10


def build_payload(to: str, message: OutboundMessage) -> dict:
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to.lstrip("+")}
    choices = message.choices
    if not choices:
        return {**base, "type": "text", "text": {"body": message.text, "preview_url": False}}
    if len(choices) <= MAX_BUTTONS:
        buttons = [
            {"type": "reply", "reply": {"id": c.id, "title": c.title[:BUTTON_TITLE_MAX]}}
            for c in choices
        ]
        return {
            **base,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": message.text},
                "action": {"buttons": buttons},
            },
        }
    rows = [{"id": c.id, "title": c.title[:ROW_TITLE_MAX]} for c in choices[:MAX_ROWS]]
    return {
        **base,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": message.text},
            "action": {"button": "Choose", "sections": [{"title": "Options", "rows": rows}]},
        },
    }


class CloudSender:
    def __init__(self, settings: ChannelSettings, secrets: Secrets) -> None:
        self._settings = settings
        self._url = f"https://graph.facebook.com/{secrets.wa_api_version}/{secrets.wa_phone_number_id}/messages"
        self._token = secrets.wa_access_token

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        payload = build_payload(to, message)
        headers = {"Authorization": f"Bearer {self._token}"}
        attempts = self._settings.max_retries + 1
        async with httpx.AsyncClient(timeout=self._settings.send_timeout_seconds) as client:
            for attempt in range(attempts):
                try:
                    resp = await client.post(self._url, json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    error = type(exc).__name__
                else:
                    if resp.status_code < 300:
                        return SentMessage(id=resp.json()["messages"][0]["id"])
                    error = f"http_{resp.status_code}"
                    if resp.status_code != 429 and resp.status_code < 500:
                        break  # client error: not retried
                if attempt < attempts - 1:
                    await asyncio.sleep(self._settings.retry_backoff_seconds * 2**attempt)
        log.warning("whatsapp_send_failed", extra={"error": error})
        raise ChannelError(error)
