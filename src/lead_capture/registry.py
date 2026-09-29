"""Builds adapters by the names in settings (research R16). Vendor modules are imported lazily
so a missing optional SDK never breaks tests that use fakes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lead_capture.ports.channel import MessagingChannel
from lead_capture.ports.clock import Clock
from lead_capture.ports.leads import LeadRepository
from lead_capture.ports.llm import LLMClient
from lead_capture.ports.locks import ConversationLock
from lead_capture.ports.queue import TurnQueue
from lead_capture.settings import Secrets, Settings


def _pick(kind: str, name: str, table: dict[str, Callable[[], Any]]) -> Any:
    try:
        factory = table[name]
    except KeyError:
        raise ValueError(
            f"unknown {kind} provider {name!r}; expected one of {sorted(table)}"
        ) from None
    return factory()


def build_llm(s: Settings, secrets: Secrets) -> LLMClient:
    def anthropic():
        from lead_capture.adapters.llm.anthropic import AnthropicLLMClient

        return AnthropicLLMClient(s.llm, api_key=secrets.anthropic_api_key)

    def fake():
        from lead_capture.adapters.llm.fake import FakeLLMClient

        return FakeLLMClient()

    def stub():
        from lead_capture.adapters.llm.stub import StubLLMClient

        return StubLLMClient(s.llm)

    return _pick("llm", s.llm.provider, {"anthropic": anthropic, "fake": fake, "stub": stub})


def build_channel(s: Settings, secrets: Secrets) -> MessagingChannel:
    def whatsapp_cloud():
        from lead_capture.adapters.channels.whatsapp_cloud.channel import WhatsAppCloudChannel

        return WhatsAppCloudChannel(s.channel, secrets)

    def fake():
        from lead_capture.adapters.channels.fake import FakeChannel

        return FakeChannel()

    return _pick("channel", s.channel.provider, {"whatsapp_cloud": whatsapp_cloud, "fake": fake})


def build_lead_repository(s: Settings, secrets: Secrets) -> LeadRepository:
    def google_sheet():
        from lead_capture.adapters.leads.google_sheet import GoogleSheetLeadRepository

        return GoogleSheetLeadRepository.from_secrets(secrets, timezone=s.ops.timezone)

    def in_memory():
        from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository

        return InMemoryLeadRepository(timezone=s.ops.timezone)

    return _pick(
        "leads", s.leads.repository, {"google_sheet": google_sheet, "in_memory": in_memory}
    )


def build_queue(s: Settings) -> TurnQueue:
    def inprocess():
        from lead_capture.adapters.queue_inprocess import InProcessTurnQueue

        return InProcessTurnQueue()

    return _pick("queue", s.queue.provider, {"inprocess": inprocess})


def build_lock(s: Settings) -> ConversationLock:
    def memory():
        from lead_capture.adapters.locks_memory import InMemoryConversationLock

        return InMemoryConversationLock()

    return _pick("lock", s.lock.provider, {"memory": memory})


def build_clock(s: Settings) -> Clock:
    def system():
        from lead_capture.adapters.clock import SystemClock

        return SystemClock(s.ops.timezone)

    def frozen():
        from datetime import datetime

        from lead_capture.adapters.clock import FrozenClock

        return FrozenClock(datetime.now(), s.ops.timezone)

    return _pick("clock", s.clock.provider, {"system": system, "frozen": frozen})
