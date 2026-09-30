"""Wiring: every adapter and the requirement schema, built once from settings.

Why: the app, CLI, jobs, evals and tests all need the same set of collaborators. Building
them in one place (with overrides for tests) keeps construction out of business code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import sessionmaker

from lead_capture import registry
from lead_capture.domain.schema import RequirementSchema, get_schema, load_schema
from lead_capture.ports.channel import MessagingChannel
from lead_capture.ports.clock import Clock
from lead_capture.ports.leads import LeadRepository
from lead_capture.ports.llm import LLMClient
from lead_capture.ports.locks import ConversationLock
from lead_capture.ports.queue import TurnQueue
from lead_capture.settings import ROOT, Secrets, Settings
from lead_capture.store.db import make_engine, make_session_factory


@dataclass
class Services:
    """Everything a turn, job or command needs."""

    settings: Settings
    secrets: Secrets
    schema: RequirementSchema
    llm: LLMClient
    channel: MessagingChannel
    leads: LeadRepository
    queue: TurnQueue
    lock: ConversationLock
    clock: Clock
    sessions: sessionmaker
    extras: dict[str, Any] = field(default_factory=dict)


def build_services(
    settings: Settings, secrets: Secrets | None = None, **overrides: Any
) -> Services:
    """Build from settings; any collaborator can be overridden (tests pass fakes)."""
    secrets = secrets or Secrets()
    schema = overrides.pop("schema", None)
    if schema is None:
        path = ROOT / settings.schema_files.requirement_file
        schema = get_schema(path) if path.exists() else load_schema(path)
    sessions = overrides.pop("sessions", None)
    if sessions is None:
        sessions = make_session_factory(make_engine(secrets.database_url))
    return Services(
        settings=settings,
        secrets=secrets,
        schema=schema,
        llm=overrides.pop("llm", None) or registry.build_llm(settings, secrets, schema),
        channel=overrides.pop("channel", None) or registry.build_channel(settings, secrets),
        leads=overrides.pop("leads", None)
        or registry.build_lead_repository(settings, secrets, schema),
        queue=overrides.pop("queue", None) or registry.build_queue(settings),
        lock=overrides.pop("lock", None) or registry.build_lock(settings),
        clock=overrides.pop("clock", None) or registry.build_clock(settings),
        sessions=sessions,
        extras=overrides,
    )
