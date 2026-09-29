from fastapi.testclient import TestClient

from lead_capture.adapters.channels.fake import FakeChannel
from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
from lead_capture.adapters.llm.fake import FakeLLMClient
from lead_capture.app import create_app
from lead_capture.services import build_services
from lead_capture.settings import load_settings


def make(session_factory, handler=None):
    services = build_services(
        load_settings(),
        llm=FakeLLMClient(),
        channel=FakeChannel(),
        leads=InMemoryLeadRepository(),
        sessions=session_factory,
    )
    return services, TestClient(create_app(services, handler))


def test_healthz(session_factory):
    _, client = make(session_factory)
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": "ok", "outbox_pending": 0}


def test_webhook_verify_and_signature(session_factory):
    received = []

    async def handler(services, messages):
        received.extend(messages)

    services, client = make(session_factory, handler)
    ok = client.get("/webhooks/fake", params={"hub.verify_token": "fake", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert client.get("/webhooks/fake", params={"hub.verify_token": "no"}).status_code == 403
    headers, body = services.channel.make_payload([{"id": "m1", "contact": "+91", "text": "hi"}])
    assert client.post("/webhooks/fake", content=body, headers=headers).status_code == 200
    assert [m.id for m in received] == ["m1"]
    bad_headers, _ = services.channel.make_payload([], valid=False)
    assert client.post("/webhooks/fake", content=body, headers=bad_headers).status_code == 401
    assert client.get("/webhooks/unknown", params={}).status_code == 404
