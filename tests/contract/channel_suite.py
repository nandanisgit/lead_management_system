"""Shared contract suite for every MessagingChannel adapter.

``ctx`` provides: ``channel``, ``payload(messages, valid=True) -> (headers, body)`` where each
message is a dict with keys id, contact, text, is_echo (optional), choice_id (optional).
Optionally ``message_id(raw_id)``: the ID the channel reports for a raw test ID (channels
that build their own IDs, e.g. Telegram's "tg-<update_id>"); identity by default.
"""

from __future__ import annotations

import pytest

from lead_capture.ports.channel import (
    Capabilities,
    Choice,
    InboundMessage,
    MessagingChannel,
    OutboundMessage,
    SignatureError,
    as_numbered_text,
    fit_to_capabilities,
)


def check_is_channel(ctx):
    assert isinstance(ctx.channel, MessagingChannel)
    assert isinstance(ctx.channel.capabilities, Capabilities)
    assert ctx.channel.name


def check_inbound_normalised(ctx):
    headers, body = ctx.payload([{"id": "m1", "contact": "+919999900001", "text": "hi"}])
    msgs = ctx.channel.parse_inbound(headers, body)
    assert len(msgs) == 1 and isinstance(msgs[0], InboundMessage)
    expected_id = getattr(ctx, "message_id", lambda raw: raw)("m1")
    assert msgs[0].id == expected_id and msgs[0].text == "hi" and msgs[0].type == "text"
    assert msgs[0].contact.endswith("9999900001")


def check_duplicate_ids_preserved(ctx):
    # Dedupe is the store's job (unique wa_message_id), not the channel's.
    headers, body = ctx.payload(
        [
            {"id": "dup", "contact": "+919999900001", "text": "a"},
            {"id": "dup", "contact": "+919999900001", "text": "a"},
        ]
    )
    expected_id = getattr(ctx, "message_id", lambda raw: raw)("dup")
    assert [m.id for m in ctx.channel.parse_inbound(headers, body)] == [expected_id] * 2


def check_echo_flag(ctx):
    headers, body = ctx.payload(
        [{"id": "e1", "contact": "+919999900001", "text": "from ops", "is_echo": True}]
    )
    assert ctx.channel.parse_inbound(headers, body)[0].is_echo is True


def check_bad_signature_rejected(ctx):
    headers, body = ctx.payload(
        [{"id": "m1", "contact": "+919999900001", "text": "hi"}], valid=False
    )
    with pytest.raises(SignatureError):
        ctx.channel.parse_inbound(headers, body)


async def check_send_returns_id(ctx):
    sent = await ctx.channel.send("+919999900001", OutboundMessage(text="hello"))
    assert sent.id


def check_choices_degrade_to_numbered_text():
    msg = OutboundMessage(
        text="Pick one", choices=[Choice(id="a", title="A"), Choice(id="b", title="B")]
    )
    no_buttons = Capabilities(
        max_buttons=0, max_list_rows=0, has_service_window=False, window_hours=0
    )
    assert fit_to_capabilities(msg, no_buttons) == as_numbered_text(msg)
    assert "1. A" in as_numbered_text(msg).text and not as_numbered_text(msg).choices


SYNC_CHECKS = [
    check_is_channel,
    check_inbound_normalised,
    check_duplicate_ids_preserved,
    check_echo_flag,
    check_bad_signature_rejected,
]
ASYNC_CHECKS = [check_send_returns_id]
