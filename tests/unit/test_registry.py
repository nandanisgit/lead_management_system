import pytest

from lead_capture import registry
from lead_capture.adapters.channels.fake import FakeChannel
from lead_capture.adapters.clock import SystemClock
from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
from lead_capture.adapters.llm.fake import FakeLLMClient
from lead_capture.adapters.locks_memory import InMemoryConversationLock
from lead_capture.adapters.queue_inprocess import InProcessTurnQueue
from lead_capture.settings import Secrets, load_settings


@pytest.fixture
def s():
    return load_settings(
        llm={"provider": "fake"}, channel={"provider": "fake"}, leads={"repository": "in_memory"}
    )


def test_builds_adapters_named_in_settings(s, schema):
    sec = Secrets()
    assert isinstance(registry.build_llm(s, sec, schema), FakeLLMClient)
    assert isinstance(registry.build_channel(s, sec), FakeChannel)
    assert isinstance(registry.build_lead_repository(s, sec, schema), InMemoryLeadRepository)
    assert isinstance(registry.build_queue(s), InProcessTurnQueue)
    assert isinstance(registry.build_lock(s), InMemoryConversationLock)
    assert isinstance(registry.build_clock(s), SystemClock)


def test_unknown_names_raise_clearly(s):
    s.queue.provider = "carrier-pigeon"
    with pytest.raises(ValueError, match="carrier-pigeon"):
        registry.build_queue(s)
