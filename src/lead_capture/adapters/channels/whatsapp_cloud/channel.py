"""WhatsAppCloudChannel — MessagingChannel adapter for the WhatsApp Business Cloud API."""

from __future__ import annotations

from collections.abc import Mapping

from lead_capture.adapters.channels.whatsapp_cloud import parser, signature
from lead_capture.adapters.channels.whatsapp_cloud.sender import MAX_BUTTONS, MAX_ROWS, CloudSender
from lead_capture.ports.channel import (
    Capabilities,
    InboundMessage,
    OutboundMessage,
    SentMessage,
    fit_to_capabilities,
)
from lead_capture.settings import ChannelSettings, Secrets

SERVICE_WINDOW_HOURS = 24  # WhatsApp platform rule, not a tunable


class WhatsAppCloudChannel:
    name = "whatsapp_cloud"

    def __init__(self, settings: ChannelSettings, secrets: Secrets) -> None:
        self._secrets = secrets
        self._sender = CloudSender(settings, secrets)
        self.capabilities = Capabilities(
            max_buttons=MAX_BUTTONS,
            max_list_rows=MAX_ROWS,
            has_service_window=True,
            window_hours=SERVICE_WINDOW_HOURS,
        )

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        if params.get("hub.mode") != "subscribe":
            return None
        token = self._secrets.wa_verify_token
        if not token or params.get("hub.verify_token") != token:
            return None
        return params.get("hub.challenge", "")

    def parse_inbound(self, headers: Mapping[str, str], body: bytes) -> list[InboundMessage]:
        signature.verify(headers, body, self._secrets.wa_app_secret)
        return parser.parse(body)

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        return await self._sender.send(to, fit_to_capabilities(message, self.capabilities))
