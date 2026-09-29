"""FR-030: per-number turn limits. One notice, then silence and no model calls until the period
passes. Limits come from settings (conversation.max_turns_per_contact_per_hour / _per_day)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy.orm import Session

from lead_capture.settings import ConversationSettings
from lead_capture.store import queries

log = logging.getLogger(__name__)


class Verdict(StrEnum):
    OK = "ok"
    NOTIFY = "notify"  # limit just reached: send the one notice
    SILENT = "silent"  # already limited: do nothing


def check(db: Session, contact, now: datetime, limits: ConversationSettings) -> Verdict:
    if contact.rate_limited_until and now < contact.rate_limited_until:
        return Verdict.SILENT
    hour = queries.inbound_count_since(db, contact.id, now - timedelta(hours=1))
    day = queries.inbound_count_since(db, contact.id, now - timedelta(days=1))
    if day > limits.max_turns_per_contact_per_day:
        contact.rate_limited_until = now + timedelta(days=1)
    elif hour > limits.max_turns_per_contact_per_hour:
        contact.rate_limited_until = now + timedelta(hours=1)
    else:
        return Verdict.OK
    log.warning("rate_limited", extra={"contact_id": contact.id, "hour": hour, "day": day})
    return Verdict.NOTIFY
