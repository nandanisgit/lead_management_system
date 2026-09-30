"""Operations-hours logic for closing and handoff messages.

Why: the tutee is told when the team will get in touch (FR-018), and handoffs show a reply-by
time; both depend on the operations hours in settings (ops.*), every day of the week.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from lead_capture.settings import OpsSettings


class ContactWhen(StrEnum):
    """When the operations team will get in touch, relative to their working hours."""

    TODAY = "today"
    AFTER_START_TODAY = "after_start_today"
    AFTER_START_TOMORROW = "after_start_tomorrow"


def when_team_contacts(now: datetime, ops: OpsSettings) -> ContactWhen:
    """FR-018: pick the closing message variant from the time of confirmation."""
    local = now.astimezone(ZoneInfo(ops.timezone)).time()
    if local < ops.hours_start:
        return ContactWhen.AFTER_START_TODAY
    if local >= ops.hours_end:
        return ContactWhen.AFTER_START_TOMORROW
    return ContactWhen.TODAY


def reply_by(last_inbound: datetime, window_hours: float) -> datetime:
    """When the channel's reply window closes — the deadline for a human reply after handoff."""
    return last_inbound + timedelta(hours=window_hours)


def format_ist(at: datetime, timezone: str, fmt: str) -> str:
    """A timestamp in the operations time zone, in the sheet's configured format."""
    return at.astimezone(ZoneInfo(timezone)).strftime(fmt)
