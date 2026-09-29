"""Wiring: builds every adapter from settings once, for the app, CLI, jobs and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import sessionmaker

from lead_capture import registry
from lead_capture.domain.lists import AllowedLists, get_lists
from lead_capture.ports.channel import MessagingChannel
from lead_capture.ports.clock import Clock
from lead_capture.ports.leads import LeadRepository
from lead_capture.ports.llm import LLMClient
from lead_capture.ports.locks import ConversationLock
from lead_capture.ports.queue import TurnQueue
from lead_capture.settings import Secrets, Settings
from lead_capture.store.db import make_engine, make_session_factory


@dataclass
class Services:
    settings: Settings
    secrets: Secrets
    llm: LLMClient
    channel: MessagingChannel
    leads: LeadRepository
    queue: TurnQueue
    lock: ConversationLock
    clock: Clock
    lists: AllowedLists
    sessions: sessionmaker
    extras: dict[str, Any] = field(default_factory=dict)


def build_services(
    settings: Settings, secrets: Secrets | None = None, **overrides: Any
) -> Services:
    """Build from settings; any adapter can be overridden (tests pass fakes)."""
    secrets = secrets or Secrets()
    sessions = overrides.pop("sessions", None)
    if sessions is None:
        sessions = make_session_factory(make_engine(secrets.database_url))
    return Services(
        settings=settings,
        secrets=secrets,
        llm=overrides.pop("llm", None) or registry.build_llm(settings, secrets),
        channel=overrides.pop("channel", None) or registry.build_channel(settings, secrets),
        leads=overrides.pop("leads", None) or registry.build_lead_repository(settings, secrets),
        queue=overrides.pop("queue", None) or registry.build_queue(settings),
        lock=overrides.pop("lock", None) or registry.build_lock(settings),
        clock=overrides.pop("clock", None) or registry.build_clock(settings),
        lists=overrides.pop("lists", None) or get_lists(),
        sessions=sessions,
        extras=overrides,
    )
