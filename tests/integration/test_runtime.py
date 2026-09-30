import time

from fastapi.testclient import TestClient

from lead_capture.adapters.channels.fake import FakeChannel
from lead_capture.adapters.llm.fake import FakeLLMClient
from lead_capture.runtime import create_runtime_app
from lead_capture.services import build_services
from lead_capture.settings import load_settings
from tests.conftest import memory_repo


def test_webhook_to_reply_through_the_running_app(session_factory):
    services = build_services(
        load_settings(conversation={"debounce_ms": 0}),
        llm=FakeLLMClient(),
        channel=FakeChannel(),
        leads=memory_repo(),
        sessions=session_factory,
    )
    with TestClient(create_runtime_app(services)) as client:
        headers, body = services.channel.make_payload(
            [{"id": "m1", "contact": "+919999900001", "text": "Hi, need a tutor"}]
        )
        assert client.post("/webhooks/fake", content=body, headers=headers).status_code == 200
        deadline = time.time() + 3
        while not services.channel.sent and time.time() < deadline:
            time.sleep(0.02)
    assert services.channel.sent and "go ahead" in services.channel.sent[0][1].text
