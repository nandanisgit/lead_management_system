import hashlib
import hmac
import json
from pathlib import Path

import pytest

from lead_capture.adapters.channels.whatsapp_cloud.channel import WhatsAppCloudChannel
from lead_capture.ports.channel import SignatureError
from lead_capture.settings import Secrets, load_settings
from tests.contract.channel_suite import ASYNC_CHECKS, SYNC_CHECKS

FIX = Path(__file__).parent / "fixtures" / "whatsapp"
SECRET = "app-secret"


def secrets() -> Secrets:
    return Secrets(
        wa_app_secret=SECRET,
        wa_verify_token="verify-me",
        wa_access_token="token",
        wa_phone_number_id="PNID",
        wa_api_version="v23.0",
    )


def channel() -> WhatsAppCloudChannel:
    return WhatsAppCloudChannel(load_settings().channel, secrets())


def signed(body: bytes, valid: bool = True) -> dict:
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest() if valid else "0" * 64
    return {"x-hub-signature-256": f"sha256={sig}"}


def fixture(name: str) -> bytes:
    return (FIX / f"{name}.json").read_bytes()


class Ctx:
    def __init__(self, sender_mock=None):
        self.channel = channel()

    def payload(self, messages, valid=True):
        normal, echoes = [], []
        for m in messages:
            wa = {
                "from": m["contact"].lstrip("+"),
                "id": m["id"],
                "timestamp": "1790700000",
                "type": "text",
                "text": {"body": m["text"]},
            }
            if m.get("is_echo"):
                wa = {**wa, "from": "911100000000", "to": m["contact"].lstrip("+")}
                echoes.append(wa)
            else:
                normal.append(wa)
        changes = []
        if normal:
            changes.append({"field": "messages", "value": {"messages": normal}})
        if echoes:
            changes.append({"field": "smb_message_echoes", "value": {"message_echoes": echoes}})
        body = json.dumps({"entry": [{"changes": changes}]}).encode()
        return signed(body, valid), body


@pytest.mark.parametrize("check", SYNC_CHECKS, ids=lambda c: c.__name__)
def test_channel_suite(check):
    check(Ctx())


@pytest.mark.parametrize("check", ASYNC_CHECKS, ids=lambda c: c.__name__)
async def test_channel_suite_async(check, respx_mock):
    respx_mock.post("https://graph.facebook.com/v23.0/PNID/messages").respond(
        200, json={"messages": [{"id": "wamid.OUT1"}]}
    )
    await check(Ctx())


def test_verify_subscription():
    ch = channel()
    params = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "123"}
    assert ch.verify_subscription(params) == "123"
    assert ch.verify_subscription({**params, "hub.verify_token": "wrong"}) is None
    assert ch.verify_subscription({**params, "hub.mode": "unsubscribe"}) is None


def test_signature_required():
    body = fixture("text")
    with pytest.raises(SignatureError):
        channel().parse_inbound({}, body)
    with pytest.raises(SignatureError):
        channel().parse_inbound(signed(body, valid=False), body)


def test_text_message_and_profile_name():
    body = fixture("text")
    [m] = channel().parse_inbound(signed(body), body)
    assert m.id == "wamid.TEXT1" and m.contact == "+919999900001" and m.type == "text"
    assert m.text.startswith("Hi, need") and m.profile_name == "Priya" and not m.is_echo
    assert m.timestamp.year == 2026


def test_button_and_list_replies():
    body = fixture("button_reply")
    [b] = channel().parse_inbound(signed(body), body)
    assert b.type == "interactive" and b.choice_id == "mode:home" and b.text == "Home"
    body = fixture("list_reply")
    [lst] = channel().parse_inbound(signed(body), body)
    assert lst.choice_id == "board:CBSE" and lst.text == "CBSE"


def test_referral_source():
    body = fixture("referral")
    [m] = channel().parse_inbound(signed(body), body)
    assert m.referral_source == "CAMPAIGN_123" and m.profile_name == "Amit"


def test_echo_from_business_app():
    body = fixture("echo")
    [m] = channel().parse_inbound(signed(body), body)
    assert m.is_echo and m.contact == "+919999900001" and m.text.startswith("Hi, this is Ravi")


def test_statuses_ignored_and_unsupported_types_marked():
    body = fixture("statuses")
    assert channel().parse_inbound(signed(body), body) == []
    body = fixture("audio")
    [m] = channel().parse_inbound(signed(body), body)
    assert m.type == "unsupported" and m.text is None


def test_capabilities():
    caps = channel().capabilities
    assert (caps.max_buttons, caps.max_list_rows, caps.window_hours) == (3, 10, 24)
    assert caps.has_service_window
