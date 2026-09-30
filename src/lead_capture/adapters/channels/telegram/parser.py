"""Telegram webhook ``Update`` → normalised InboundMessage list (contracts/telegram-webhook.md).

Why a separate module: parsing is pure (no network, no secrets), so it can be tested on
recorded payloads alone, like the WhatsApp parser.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from lead_capture.ports.channel import InboundMessage

ADDRESS_PREFIX = "tg:"  # channel address of a Telegram chat: "tg:<chat id>"
MESSAGE_ID_PREFIX = "tg-"  # dedupe key: "tg-<update_id>" (unique per bot)
START_COMMAND = "/start"  # Telegram's first message; "/start <payload>" carries a campaign ID
PRIVATE_CHAT = "private"


@dataclass(frozen=True)
class Tap:
    """A button tap that Telegram expects us to acknowledge (answerCallbackQuery)."""

    address: str
    callback_id: str


def address(chat_id: int | str) -> str:
    """Channel address for a Telegram chat ID."""
    return f"{ADDRESS_PREFIX}{chat_id}"


def chat_id(address_: str) -> str:
    """Telegram chat ID from a channel address (inverse of ``address``)."""
    return address_.removeprefix(ADDRESS_PREFIX)


def _ts(value: Any) -> datetime:
    """Unix time → aware UTC datetime (now, if missing or malformed)."""
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _message(update_id: Any, msg: dict) -> InboundMessage | None:
    """A private-chat message: text, a shared contact, or anything else (unsupported)."""
    chat = msg.get("chat") or {}
    if chat.get("type") != PRIVATE_CHAT or "id" not in chat:
        return None  # groups and channels are not tutees
    sender = msg.get("from") or {}
    common = {
        "id": f"{MESSAGE_ID_PREFIX}{update_id}",
        "contact": address(chat["id"]),
        "profile_name": sender.get("first_name"),
        "timestamp": _ts(msg.get("date")),
    }
    if "text" in msg:
        text = str(msg["text"])
        referral = None
        if text.split(" ", 1)[0] == START_COMMAND:
            referral = text[len(START_COMMAND) :].strip() or None
        return InboundMessage(type="text", text=text, referral_source=referral, **common)
    if "contact" in msg:
        phone = (msg["contact"] or {}).get("phone_number")
        return InboundMessage(type="contact", shared_phone=phone, **common)
    return InboundMessage(type="unsupported", **common)


def _callback(update_id: Any, cb: dict) -> tuple[InboundMessage | None, Tap | None]:
    """An inline-button tap: its ``data`` is the choice ID we sent."""
    chat = ((cb.get("message") or {}).get("chat")) or {}
    if chat.get("type") != PRIVATE_CHAT or "id" not in chat or not cb.get("data"):
        return None, None
    addr = address(chat["id"])
    msg = InboundMessage(
        id=f"{MESSAGE_ID_PREFIX}{update_id}",
        contact=addr,
        type="interactive",
        choice_id=str(cb["data"]),
        profile_name=(cb.get("from") or {}).get("first_name"),
        # a tap carries no time of its own (message.date is when *we* sent the buttons)
        timestamp=datetime.now(UTC),
    )
    return msg, Tap(addr, str(cb["id"])) if cb.get("id") else None


def parse(body: bytes) -> tuple[list[InboundMessage], list[Tap]]:
    """Normalise one Update (webhook) or a list of Updates (getUpdates-style).

    Returns the messages plus the button taps to acknowledge. Unknown update kinds (edited
    messages, channel posts, …) are ignored.
    """
    data = json.loads(body or b"{}")
    updates = data if isinstance(data, list) else [data]
    messages: list[InboundMessage] = []
    taps: list[Tap] = []
    for upd in updates:
        if not isinstance(upd, dict):
            continue
        uid = upd.get("update_id")
        if isinstance(upd.get("message"), dict):
            msg = _message(uid, upd["message"])
            if msg:
                messages.append(msg)
        elif isinstance(upd.get("callback_query"), dict):
            msg, tap = _callback(uid, upd["callback_query"])
            if msg:
                messages.append(msg)
            if tap:
                taps.append(tap)
    return messages, taps
