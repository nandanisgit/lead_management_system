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
    """MessagingChannel for the WhatsApp Business Cloud API (tutee-initiated replies only)."""

    name = "whatsapp_cloud"
    path_name = "whatsapp"  # webhook URL registered with Meta: /webhooks/whatsapp

    def __init__(self, settings: ChannelSettings, secrets: Secrets) -> None:
        """Build from channel settings and WhatsApp secrets (token, phone number ID, app secret)."""
        self._secrets = secrets
        self._sender = CloudSender(settings, secrets)
        self.capabilities = Capabilities(
            max_buttons=MAX_BUTTONS,
            max_list_rows=MAX_ROWS,
            has_service_window=True,
            window_hours=SERVICE_WINDOW_HOURS,
            contact_is_phone=True,  # the sender's WhatsApp number is their phone number
        )

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """Meta's webhook handshake: echo the challenge when the verify token matches."""
        if params.get("hub.mode") != "subscribe":
            return None
        token = self._secrets.wa_verify_token
        if not token or params.get("hub.verify_token") != token:
            return None
        return params.get("hub.challenge", "")

    def parse_inbound(self, headers: Mapping[str, str], body: bytes) -> list[InboundMessage]:
        """Reject unsigned/forged requests, then normalise the payload."""
        signature.verify(headers, body, self._secrets.wa_app_secret)
        return parser.parse(body)

    async def send(self, to: str, message: OutboundMessage) -> SentMessage:
        """Send a reply, degrading choices to numbered text when they exceed WhatsApp's limits."""
        return await self._sender.send(to, fit_to_capabilities(message, self.capabilities))
