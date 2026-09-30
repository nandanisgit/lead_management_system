"""TelegramChannel: the shared channel contract plus Telegram specifics.

See contracts/telegram-webhook.md.
"""

import asyncio
import json
import zlib

import httpx
import pytest
import respx

from lead_capture.adapters.channels.telegram.channel import SECRET_HEADER, TelegramChannel
from lead_capture.adapters.channels.telegram.sender import build_payload
from lead_capture.ports.channel import ChannelError, Choice, OutboundMessage, SignatureError
from lead_capture.registry import build_channel
from lead_capture.settings import Secrets, load_settings
from tests.contract.channel_suite import (
    ASYNC_CHECKS,
    check_bad_signature_rejected,
    check_duplicate_ids_preserved,
    check_inbound_normalised,
    check_is_channel,
)

TOKEN = "123456:TEST-TOKEN"
SECRET = "webhook-secret"
API = f"https://api.telegram.org/bot{TOKEN}"
CHAT = 5550001
ADDR = f"tg:{CHAT}"


def settings(**channel):
    return load_settings(channel={"provider": "telegram", "retry_backoff_seconds": 0, **channel})


def secrets(**over) -> Secrets:
    base = {"telegram_bot_token": TOKEN, "telegram_webhook_secret": SECRET}
    return Secrets(_env_file=None, **{**base, **over})


def channel(**channel_settings) -> TelegramChannel:
    return TelegramChannel(settings(**channel_settings).channel, secrets())


def headers(valid=True) -> dict:
    return {SECRET_HEADER: SECRET if valid else "wrong"}


def update_id(raw: str) -> int:
    return zlib.crc32(raw.encode())


def text_update(uid, text, chat=CHAT, chat_type="private"):
    return {
        "update_id": uid,
        "message": {
            "message_id": 7,
            "date": 1790700000,
            "chat": {"id": chat, "type": chat_type},
            "from": {"id": chat, "first_name": "Priya"},
            "text": text,
        },
    }


def body(obj) -> bytes:
    return json.dumps(obj).encode()


class Ctx:
    """Context for the shared channel suite (Telegram has no echoes)."""

    def __init__(self):
        self.channel = channel()

    def message_id(self, raw):
        return f"tg-{update_id(raw)}"

    def payload(self, messages, valid=True):
        updates = [
            text_update(update_id(m["id"]), m["text"], chat=int(m["contact"].lstrip("+")))
            for m in messages
        ]
        return headers(valid), body(updates if len(updates) > 1 else updates[0])


@pytest.mark.parametrize(
    "check",
    [
        check_is_channel,
        check_inbound_normalised,
        check_duplicate_ids_preserved,
        check_bad_signature_rejected,
    ],
    ids=lambda c: c.__name__,
)
def test_channel_suite(check):
    check(Ctx())


@pytest.mark.parametrize("check", ASYNC_CHECKS, ids=lambda c: c.__name__)
@respx.mock
async def test_channel_suite_async(check):
    respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )
    ctx = Ctx()
    ctx.channel = channel()
    await check(ctx)


# ---------------------------------------------------------------- inbound


def parse(obj, valid=True):
    return channel().parse_inbound(headers(valid), body(obj))


def test_text_message():
    [m] = parse(text_update(42, "Hi, need a tutor"))
    assert (m.id, m.contact, m.type, m.text, m.profile_name) == (
        "tg-42",
        ADDR,
        "text",
        "Hi, need a tutor",
        "Priya",
    )
    assert m.timestamp.year == 2026


def test_start_payload_is_the_referral_source():
    [m] = parse(text_update(1, "/start campaign-diwali"))
    assert m.referral_source == "campaign-diwali"
    [m] = parse(text_update(2, "/start"))
    assert m.referral_source is None


def test_shared_contact():
    upd = text_update(3, "x")
    del upd["message"]["text"]
    upd["message"]["contact"] = {"phone_number": "919876543210", "first_name": "Priya"}
    [m] = parse(upd)
    assert m.type == "contact" and m.shared_phone == "919876543210" and m.text is None


def test_voice_note_is_unsupported():
    upd = text_update(4, "x")
    del upd["message"]["text"]
    upd["message"]["voice"] = {"file_id": "abc", "duration": 3}
    [m] = parse(upd)
    assert m.type == "unsupported"


def test_button_tap():
    upd = {
        "update_id": 5,
        "callback_query": {
            "id": "cb-1",
            "data": "mode:home",
            "from": {"id": CHAT, "first_name": "Priya"},
            "message": {
                "message_id": 9,
                "date": 1790700000,
                "chat": {"id": CHAT, "type": "private"},
            },
        },
    }
    [m] = parse(upd)
    assert (m.type, m.choice_id, m.contact) == ("interactive", "mode:home", ADDR)


def test_groups_and_other_updates_ignored():
    assert parse(text_update(6, "hi", chat=-100, chat_type="group")) == []
    assert parse({"update_id": 7, "edited_message": {"text": "x"}}) == []


def test_missing_or_wrong_secret_rejected():
    with pytest.raises(SignatureError):
        parse(text_update(8, "hi"), valid=False)
    with pytest.raises(SignatureError):
        TelegramChannel(settings().channel, secrets(telegram_webhook_secret=None)).parse_inbound(
            headers(), body(text_update(8, "hi"))
        )


def test_no_get_handshake():
    assert channel().verify_subscription({"hub.challenge": "1"}) is None


# ---------------------------------------------------------------- outbound


def test_payload_plain_text_removes_keyboard():
    p = build_payload(ADDR, OutboundMessage(text="Hello"), 1)
    assert p == {"chat_id": str(CHAT), "text": "Hello", "reply_markup": {"remove_keyboard": True}}


def test_payload_choices_become_inline_buttons():
    msg = OutboundMessage(
        text="Mode?",
        choices=[Choice(id="mode:online", title="Online"), Choice(id="mode:home", title="Home")],
    )
    kb = build_payload(ADDR, msg, 2)["reply_markup"]["inline_keyboard"]
    assert kb == [
        [
            {"text": "Online", "callback_data": "mode:online"},
            {"text": "Home", "callback_data": "mode:home"},
        ]
    ]
    assert len(build_payload(ADDR, msg, 1)["reply_markup"]["inline_keyboard"]) == 2


def test_payload_long_choice_ids_fall_back_to_numbered_text():
    msg = OutboundMessage(text="Pick", choices=[Choice(id="x" * 65, title="A")])
    p = build_payload(ADDR, msg, 1)
    assert "1. A" in p["text"] and "inline_keyboard" not in p["reply_markup"]


def test_payload_phone_request_is_a_contact_button():
    msg = OutboundMessage(text="Your number?", phone_request_label="Share my phone number")
    kb = build_payload(ADDR, msg, 1)["reply_markup"]
    assert kb["keyboard"] == [[{"text": "Share my phone number", "request_contact": True}]]
    assert kb["one_time_keyboard"] is True


@respx.mock
async def test_tap_acknowledged_once_and_reply_sent():
    ack = respx.post(f"{API}/answerCallbackQuery").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": True})
    )
    send = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})
    )
    ch = channel()
    upd = {
        "update_id": 9,
        "callback_query": {
            "id": "cb-9",
            "data": "consent:yes",
            "message": {
                "message_id": 1,
                "date": 1790700000,
                "chat": {"id": CHAT, "type": "private"},
            },
        },
    }
    ch.parse_inbound(headers(), body(upd))
    await asyncio.sleep(0.05)  # the acknowledgement runs in the background
    sent = await ch.send(ADDR, OutboundMessage(text="Great!"))
    assert sent.id == f"tg-out-{CHAT}-77"
    assert json.loads(ack.calls.last.request.content) == {"callback_query_id": "cb-9"}
    assert json.loads(send.calls.last.request.content)["chat_id"] == str(CHAT)
    await ch.send(ADDR, OutboundMessage(text="again"))
    assert ack.call_count == 1  # each tap acknowledged once


@respx.mock
async def test_retries_429_and_5xx_then_succeeds():
    route = respx.post(f"{API}/sendMessage").mock(
        side_effect=[
            httpx.Response(429, json={"ok": False}),
            httpx.Response(502),
            httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}),
        ]
    )
    await channel(max_retries=2).send(ADDR, OutboundMessage(text="hi"))
    assert route.call_count == 3


@respx.mock
async def test_blocked_user_is_not_retried():
    route = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(403, json={"ok": False, "description": "blocked"})
    )
    with pytest.raises(ChannelError, match="403"):
        await channel(max_retries=3).send(ADDR, OutboundMessage(text="hi"))
    assert route.call_count == 1


@respx.mock
async def test_register_webhook_sends_secret_and_path():
    route = respx.post(f"{API}/setWebhook").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": True})
    )
    await channel().register_webhook("https://abc.trycloudflare.com/")
    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "url": "https://abc.trycloudflare.com/webhooks/telegram",
        "secret_token": SECRET,
        "allowed_updates": ["message", "callback_query"],
    }


def test_registry_builds_telegram_channel():
    assert isinstance(build_channel(settings(), secrets()), TelegramChannel)


def test_capabilities():
    caps = channel().capabilities
    assert caps.can_request_phone and not caps.contact_is_phone and not caps.has_service_window


@respx.mock
async def test_tap_is_acknowledged_immediately_inside_the_server():
    ack = respx.post(f"{API}/answerCallbackQuery").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": True})
    )
    upd = {
        "update_id": 10,
        "callback_query": {
            "id": "cb-10",
            "data": "consent:yes",
            "message": {
                "message_id": 1,
                "date": 1000,
                "chat": {"id": CHAT, "type": "private"},
            },
        },
    }
    [m] = channel().parse_inbound(headers(), body(upd))  # running loop: ack in background
    await asyncio.sleep(0.05)
    assert ack.call_count == 1
    assert m.timestamp.year >= 2026  # the tap's own time, not the old message's date
