"""WhatsApp Cloud API webhook payload → normalised InboundMessage list."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from lead_capture.ports.channel import InboundMessage


def _ts(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _normalise(raw: dict, contact: str, profile: str | None, is_echo: bool) -> InboundMessage:
    kind = raw.get("type")
    text = choice_id = None
    msg_type = "unsupported"
    if kind == "text":
        msg_type, text = "text", (raw.get("text") or {}).get("body")
    elif kind == "interactive":
        inter = raw.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        msg_type, text, choice_id = "interactive", reply.get("title"), reply.get("id")
    elif kind == "button":  # quick-reply button on a message
        msg_type, text = "text", (raw.get("button") or {}).get("text")
    referral = (raw.get("referral") or {}).get("source_id")
    return InboundMessage(
        id=raw["id"],
        contact="+" + contact.lstrip("+"),
        type=msg_type,
        text=text,
        choice_id=choice_id,
        profile_name=profile,
        referral_source=referral,
        timestamp=_ts(raw.get("timestamp")),
        is_echo=is_echo,
    )


def parse(body: bytes) -> list[InboundMessage]:
    data = json.loads(body or b"{}")
    out: list[InboundMessage] = []
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", [])
            }
            for raw in value.get("messages", []):
                sender = raw.get("from", "")
                out.append(_normalise(raw, sender, names.get(sender), is_echo=False))
            for raw in value.get("message_echoes", []):
                out.append(_normalise(raw, raw.get("to", ""), None, is_echo=True))
            # statuses[] and anything else: ignored in v1
    return out
