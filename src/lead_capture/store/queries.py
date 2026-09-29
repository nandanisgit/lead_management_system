"""Common queries on the bot working store."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lead_capture.ports.llm import TokenUsage
from lead_capture.store.models import ACTIVE_STATES, Contact, Conversation, Message, UsageEvent


def get_or_create_contact(s: Session, wa_number: str, profile_name: str | None = None) -> Contact:
    contact = s.scalar(select(Contact).where(Contact.wa_number == wa_number))
    if contact is None:
        contact = Contact(wa_number=wa_number, wa_profile_name=profile_name)
        s.add(contact)
        s.flush()
    elif profile_name and contact.wa_profile_name != profile_name:
        contact.wa_profile_name = profile_name
    return contact


def store_message(
    s: Session,
    contact_id: int,
    conversation_id: int | None,
    wa_message_id: str,
    direction: str,
    type_: str,
    body: str,
    created_at: datetime | None = None,
) -> bool:
    """Store a message idempotently. Returns False if this message ID was already stored."""
    if s.scalar(select(Message.id).where(Message.wa_message_id == wa_message_id)) is not None:
        return False
    msg = Message(
        contact_id=contact_id,
        conversation_id=conversation_id,
        wa_message_id=wa_message_id,
        direction=direction,
        type=type_,
        body=body or "",
    )
    if created_at is not None:
        msg.created_at = created_at
    try:
        with s.begin_nested():
            s.add(msg)
    except IntegrityError:  # concurrent duplicate
        return False
    return True


def active_conversation(s: Session, contact_id: int, student_key: str | None = None):
    q = select(Conversation).where(
        Conversation.contact_id == contact_id, Conversation.state.in_(ACTIVE_STATES)
    )
    if student_key is not None:
        q = q.where(Conversation.student_key == student_key)
    return s.scalars(q.order_by(Conversation.updated_at.desc())).first()


def latest_conversation(s: Session, contact_id: int):
    return s.scalars(
        select(Conversation)
        .where(Conversation.contact_id == contact_id)
        .order_by(Conversation.id.desc())
    ).first()


def start_conversation(s: Session, contact_id: int, source: str = "organic", **kw) -> Conversation:
    conv = Conversation(contact_id=contact_id, source=source, collected={}, **kw)
    s.add(conv)
    s.flush()
    return conv


def transcript(s: Session, conversation_id: int, limit: int) -> list[Message]:
    rows = s.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.direction.in_(("in", "out")))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def inbound_count_since(s: Session, contact_id: int, since: datetime) -> int:
    return s.scalar(
        select(func.count(Message.id)).where(
            Message.contact_id == contact_id,
            Message.direction == "in",
            Message.created_at >= since,
        )
    )


def record_usage(
    s: Session, conversation_id: int | None, kind: str, usage: TokenUsage | None = None
) -> None:
    s.add(
        UsageEvent(
            conversation_id=conversation_id,
            kind=kind,
            model=usage.model if usage else None,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            cache_read_tokens=usage.cache_read_tokens if usage else 0,
            cache_write_tokens=usage.cache_write_tokens if usage else 0,
        )
    )
