import json

import httpx
import pytest

from lead_capture.adapters.channels.whatsapp_cloud.channel import WhatsAppCloudChannel
from lead_capture.ports.channel import ChannelError, Choice, OutboundMessage
from lead_capture.settings import Secrets, load_settings

URL = "https://graph.facebook.com/v23.0/PNID/messages"


def channel(**over):
    s = load_settings(channel={"retry_backoff_seconds": 0, **over})
    return WhatsAppCloudChannel(
        s.channel, Secrets(wa_access_token="tok", wa_phone_number_id="PNID", wa_api_version="v23.0")
    )


def sent_json(route):
    return json.loads(route.calls.last.request.content)


async def test_text(respx_mock):
    route = respx_mock.post(URL).respond(200, json={"messages": [{"id": "wamid.X"}]})
    sent = await channel().send("+919999900001", OutboundMessage(text="Hello"))
    assert sent.id == "wamid.X"
    body = sent_json(route)
    assert body["to"] == "919999900001" and body["type"] == "text"
    assert body["text"]["body"] == "Hello"
    assert route.calls.last.request.headers["authorization"] == "Bearer tok"


async def test_up_to_three_choices_become_buttons(respx_mock):
    route = respx_mock.post(URL).respond(200, json={"messages": [{"id": "x"}]})
    msg = OutboundMessage(
        text="Online or home?",
        choices=[Choice(id="mode:online", title="Online"), Choice(id="mode:home", title="Home")],
    )
    await channel().send("+919999900001", msg)
    body = sent_json(route)
    assert body["type"] == "interactive" and body["interactive"]["type"] == "button"
    buttons = body["interactive"]["action"]["buttons"]
    assert [b["reply"]["id"] for b in buttons] == ["mode:online", "mode:home"]


async def test_four_to_ten_choices_become_list(respx_mock):
    route = respx_mock.post(URL).respond(200, json={"messages": [{"id": "x"}]})
    boards = ["CBSE", "ICSE", "State", "IB", "IGCSE"]
    msg = OutboundMessage(text="Board?", choices=[Choice(id=f"board:{b}", title=b) for b in boards])
    await channel().send("+919999900001", msg)
    inter = sent_json(route)["interactive"]
    assert inter["type"] == "list"
    assert [r["id"] for r in inter["action"]["sections"][0]["rows"]] == [
        f"board:{b}" for b in boards
    ]


async def test_no_template_method_exists():
    assert not hasattr(channel(), "send_template")


async def test_retries_on_429_and_5xx_then_succeeds(respx_mock):
    route = respx_mock.post(URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, json={"messages": [{"id": "ok"}]}),
        ]
    )
    sent = await channel(max_retries=3).send("+919999900001", OutboundMessage(text="hi"))
    assert sent.id == "ok" and route.call_count == 3


async def test_gives_up_after_max_retries(respx_mock):
    respx_mock.post(URL).respond(500)
    with pytest.raises(ChannelError):
        await channel(max_retries=2).send("+919999900001", OutboundMessage(text="hi"))


async def test_client_error_not_retried(respx_mock):
    route = respx_mock.post(URL).respond(400, json={"error": {"message": "bad"}})
    with pytest.raises(ChannelError):
        await channel(max_retries=3).send("+919999900001", OutboundMessage(text="hi"))
    assert route.call_count == 1
