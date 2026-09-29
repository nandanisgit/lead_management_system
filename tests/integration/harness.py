"""Test harness: real engine + dispatcher with fake channel, in-memory sheet, scripted LLM."""

from __future__ import annotations

import itertools
from datetime import datetime

from lead_capture.adapters.channels.fake import FakeChannel
from lead_capture.adapters.clock import FrozenClock
from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
from lead_capture.adapters.llm.fake import FakeLLMClient
from lead_capture.conversation.dispatcher import Dispatcher
from lead_capture.conversation.engine import Engine
from lead_capture.conversation.inbound import handle_inbound
from lead_capture.jobs.outbox import drain_once
from lead_capture.ports.channel import InboundMessage
from lead_capture.ports.llm import ExtractionResult, Signals
from lead_capture.services import build_services
from lead_capture.settings import load_settings

NUMBER = "+919999900001"
_ids = itertools.count(1)


def ext(lang="en", **fields) -> ExtractionResult:
    signals = fields.pop("signals", {})
    return ExtractionResult(fields=fields, signals=Signals(language=lang, **signals))


class Harness:
    def __init__(self, session_factory, at=datetime(2026, 9, 29, 15, 0), leads=None, **over):
        conversation = {"debounce_ms": 0, **over.pop("conversation", {})}
        self.settings = load_settings(conversation=conversation, **over)
        self.llm = FakeLLMClient(
            default_reply=lambda turn, ins: f"MODEL {ins.kind} {ins.params.get('fields')}"
        )
        self.channel = FakeChannel()
        self.leads = leads or InMemoryLeadRepository()
        self.clock = FrozenClock(at)
        self.sv = build_services(
            self.settings,
            llm=self.llm,
            channel=self.channel,
            leads=self.leads,
            clock=self.clock,
            sessions=session_factory,
        )
        self.engine = Engine(self.sv, on_lead_created=lambda: drain_once(self.sv))
        self.dispatcher = Dispatcher(self.sv, self.engine)
        self.dispatcher.start()

    def script(self, *extractions: ExtractionResult) -> None:
        for e in extractions:
            self.llm.queue_extraction(e)

    async def deliver(self, *messages: InboundMessage) -> None:
        await handle_inbound(self.sv, list(messages))
        await self.dispatcher.drain()

    def message(self, text=None, choice=None, number=NUMBER, msg_id=None, **kw) -> InboundMessage:
        return InboundMessage(
            id=msg_id or f"wamid.{next(_ids)}",
            contact=number,
            type="interactive" if choice else "text",
            text=text if text is not None else (choice.split(":", 1)[1] if choice else None),
            choice_id=choice,
            timestamp=self.clock.now(),
            **kw,
        )

    async def say(self, text=None, choice=None, number=NUMBER, **kw) -> list:
        before = len(self.channel.sent)
        await self.deliver(self.message(text, choice, number, **kw))
        return [m for to, m in self.channel.sent[before:] if to == number]

    @property
    def extract_calls(self) -> int:
        return sum(1 for kind, _ in self.llm.calls if kind == "extract")

    @property
    def reply_instructions(self) -> list:
        return [ins for kind, ins in self.llm.calls if kind == "write_reply"]

    def leads_rows(self) -> list[list]:
        return self.leads.leads


async def to_summary(h: Harness, lang="en") -> None:
    """Drive a standard parent conversation up to the summary."""
    await h.say("Hi, need a maths tutor for my son")
    h.script(ext(lang, subjects=["Maths"], relationship="parent"))
    await h.say(choice="consent:yes")
    h.script(
        ext(lang, contact_name="Priya", student_name="Aarav", grade_level="Class 8", board="CBSE")
    )
    await h.say("I'm Priya, he's Aarav in class 8 CBSE")
    await h.say(choice="mode:home")
    h.script(
        ext(
            lang,
            area="Dwarka Sector 12",
            city="Delhi",
            schedule="weekdays after 5 pm",
            start_date="ASAP",
        )
    )
    await h.say("Dwarka Sector 12, Delhi. Weekdays after 5, start asap")
    h.script(ext(lang, budget_min=600, budget_unit="per_hour"))
    await h.say("600 per hour")
