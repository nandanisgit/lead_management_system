"""Builds adapters by the names in settings (research R16).

Why: swapping a vendor (model, messaging app, lead store) must be a settings change plus a
new adapter — never an edit to the engine. Vendor modules are imported lazily so tests that
use fakes never need the vendor SDKs or credentials.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lead_capture.domain.schema import RequirementSchema
from lead_capture.ports.channel import MessagingChannel
from lead_capture.ports.clock import Clock
from lead_capture.ports.leads import LeadRepository
from lead_capture.ports.llm import LLMClient
from lead_capture.ports.locks import ConversationLock
from lead_capture.ports.queue import TurnQueue
from lead_capture.settings import Secrets, Settings


def _pick(kind: str, name: str, table: dict[str, Callable[[], Any]]) -> Any:
    """Call the factory registered under ``name``; unknown names fail with the valid choices."""
    try:
        factory = table[name]
    except KeyError:
        valid = sorted(table)
        raise ValueError(f"unknown {kind} provider {name!r}; expected one of {valid}") from None
    return factory()


def build_llm(s: Settings, secrets: Secrets, schema: RequirementSchema) -> LLMClient:
    """The language-model adapter named in ``llm.provider``."""

    def anthropic():
        """Claude API adapter with the schema's field tool and conversation limits."""
        from lead_capture.adapters.llm.anthropic import AnthropicLLMClient

        return AnthropicLLMClient(
            s.llm,
            api_key=secrets.anthropic_api_key,
            fields_schema=schema.llm_fields_schema(),
            max_questions=s.conversation.max_questions_per_message,
            max_words=s.conversation.max_words_per_message,
        )

    def ollama():
        """Local Ollama server (free open models) with the same schema and limits."""
        from lead_capture.adapters.llm.ollama import OllamaLLMClient

        return OllamaLLMClient(
            s.llm,
            fields_schema=schema.llm_fields_schema(),
            max_questions=s.conversation.max_questions_per_message,
            max_words=s.conversation.max_words_per_message,
        )

    def fake():
        """Scripted fake (tests)."""
        from lead_capture.adapters.llm.fake import FakeLLMClient

        return FakeLLMClient(known_fields=schema.field_names())

    def stub():
        """Delay-only stub (load tests without model cost)."""
        from lead_capture.adapters.llm.stub import StubLLMClient

        return StubLLMClient(s.llm)

    return _pick(
        "llm",
        s.llm.provider,
        {"anthropic": anthropic, "ollama": ollama, "fake": fake, "stub": stub},
    )


def build_channel(s: Settings, secrets: Secrets) -> MessagingChannel:
    """The messaging adapter named in ``channel.provider``."""

    def whatsapp_cloud():
        """WhatsApp Business Cloud API."""
        from lead_capture.adapters.channels.whatsapp_cloud.channel import WhatsAppCloudChannel

        return WhatsAppCloudChannel(s.channel, secrets)

    def telegram():
        """Telegram Bot API (research R17)."""
        from lead_capture.adapters.channels.telegram.channel import TelegramChannel

        return TelegramChannel(s.channel, secrets)

    def fake():
        """In-memory channel (tests, `lead-capture chat`)."""
        from lead_capture.adapters.channels.fake import FakeChannel

        return FakeChannel()

    return _pick(
        "channel",
        s.channel.provider,
        {"whatsapp_cloud": whatsapp_cloud, "telegram": telegram, "fake": fake},
    )


def build_lead_repository(
    s: Settings, secrets: Secrets, schema: RequirementSchema
) -> LeadRepository:
    """The lead-register adapter named in ``leads.repository``, with layouts from the schema."""
    layouts = {"leads": schema.leads_layout(), "handoffs": schema.handoffs_layout()}

    def google_sheet():
        """The operations Google Sheet."""
        from lead_capture.adapters.leads.google_sheet import GoogleSheetLeadRepository

        return GoogleSheetLeadRepository.from_config(
            secrets,
            **layouts,
            lists_tab=schema.sheet.lists_tab.tab,
            timezone=s.ops.timezone,
            timeout_seconds=s.leads.request_timeout_seconds,
        )

    def in_memory():
        """In-memory register (tests, evals, local chat)."""
        from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository

        return InMemoryLeadRepository(**layouts, timezone=s.ops.timezone)

    return _pick(
        "leads", s.leads.repository, {"google_sheet": google_sheet, "in_memory": in_memory}
    )


def build_queue(s: Settings) -> TurnQueue:
    """The turn queue named in ``queue.provider`` (in-process now; Redis/SQS later, R14)."""

    def inprocess():
        """Queue inside this process (asyncio)."""
        from lead_capture.adapters.queue_inprocess import InProcessTurnQueue

        return InProcessTurnQueue()

    return _pick("queue", s.queue.provider, {"inprocess": inprocess})


def build_lock(s: Settings) -> ConversationLock:
    """The per-contact lock named in ``lock.provider``."""

    def memory():
        """Locks inside this process (asyncio)."""
        from lead_capture.adapters.locks_memory import InMemoryConversationLock

        return InMemoryConversationLock()

    return _pick("lock", s.lock.provider, {"memory": memory})


def build_clock(s: Settings) -> Clock:
    """The clock named in ``clock.provider`` (system, or frozen for tests)."""

    def system():
        """Real time."""
        from lead_capture.adapters.clock import SystemClock

        return SystemClock(s.ops.timezone)

    def frozen():
        """Frozen time starting now (manual testing)."""
        from datetime import datetime

        from lead_capture.adapters.clock import FrozenClock

        return FrozenClock(datetime.now(), s.ops.timezone)

    return _pick("clock", s.clock.provider, {"system": system, "frozen": frozen})
