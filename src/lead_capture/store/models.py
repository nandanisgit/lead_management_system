"""Bot working store (data-model.md). Conversation state and transcripts never go to the sheet."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from lead_capture.store.db import Base, UTCDateTime, utcnow

ACTIVE_STATES = ("awaiting_consent", "in_progress", "confirming", "stalled", "handed_over")


class Contact(Base):
    """One WhatsApp user: consent time, language, rate-limit state."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wa_number: Mapped[str] = mapped_column(String(32), unique=True)
    wa_profile_name: Mapped[str | None] = mapped_column(String(120))
    contact_name: Mapped[str | None] = mapped_column(String(60))
    relationship: Mapped[str | None] = mapped_column(String(16))
    language: Mapped[str] = mapped_column(String(4), default="en")
    consent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    rate_limited_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Conversation(Base):
    """One requirement being gathered for one student, with its lifecycle state."""

    __tablename__ = "conversations"
    __table_args__ = (
        # at most one active conversation per contact + student (FR-021)
        Index(
            "uq_active_conversation",
            "contact_id",
            "student_key",
            unique=True,
            sqlite_where=text(f"state IN {ACTIVE_STATES}"),
            postgresql_where=text(f"state IN {ACTIVE_STATES}"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(20), default="awaiting_consent")
    collected: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    student_key: Mapped[str] = mapped_column(String(80), default="")
    close_reason: Mapped[str | None] = mapped_column(String(24))
    handoff_reason: Mapped[str | None] = mapped_column(String(24))
    handoff_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    handoff_id: Mapped[str | None] = mapped_column(String(24))
    misunderstand_streak: Mapped[int] = mapped_column(Integer, default=0)
    minor_alone: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_by_minor: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(64))  # always set by the engine (config)
    lead_id: Mapped[str | None] = mapped_column(String(24))
    first_inbound_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_inbound_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_outbound_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Message(Base):
    """Transcript entry, kept for retention.transcript_days; dedupe key is the channel ID."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    wa_message_id: Mapped[str] = mapped_column(String(128), unique=True)
    direction: Mapped[str] = mapped_column(String(8))  # in / out / echo
    type: Mapped[str] = mapped_column(String(16))  # text / interactive / unsupported
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class LeadOutbox(Base):
    """Confirmed lead waiting to be written (or already written) to the lead register."""

    __tablename__ = "lead_outbox"

    lead_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    row: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending/synced/deleted
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(80))
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class UsageEvent(Base):
    """Cost tracking (research R15): IDs and counts only, no personal data."""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(12))  # extract / reply / message_out
    model: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
