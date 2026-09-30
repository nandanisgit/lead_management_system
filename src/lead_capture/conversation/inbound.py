"""Inbound handling: store each message idempotently, then queue a turn (echoes: store only)."""

from __future__ import annotations

import logging

from lead_capture.ports.channel import InboundMessage
from lead_capture.services import Services
from lead_capture.store import queries

log = logging.getLogger(__name__)


async def handle_inbound(services: Services, messages: list[InboundMessage]) -> None:
    """Store each inbound message once (dedupe on message ID) and queue a turn.

    Echoes from the Business app are stored for the transcript but never queued, so the
    bot stays silent while a human is replying. Must return fast: the webhook waits on it.
    """
    for m in messages:
        with services.sessions() as db:
            contact = queries.get_or_create_contact(db, m.contact, m.profile_name)
            conv = queries.active_conversation(db, contact.id)
            stored = queries.store_message(
                db,
                contact.id,
                conv.id if conv else None,
                m.id,
                "echo" if m.is_echo else "in",
                m.type,
                m.text or "",
                m.timestamp,
            )
            db.commit()
        if not stored:
            log.info("duplicate_message", extra={"message_id": m.id})
            continue
        if not m.is_echo:
            await services.queue.put(m.contact, m)
