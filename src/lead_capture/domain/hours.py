"""Operations-hours logic for closing and handoff messages (every day, ops.hours_start–end)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from lead_capture.settings import OpsSettings


class ContactWhen(StrEnum):
    TODAY = "today"
    AFTER_START_TODAY = "after_start_today"
    AFTER_START_TOMORROW = "after_start_tomorrow"


def when_team_contacts(now: datetime, ops: OpsSettings) -> ContactWhen:
    local = now.astimezone(ZoneInfo(ops.timezone)).time()
    if local < ops.hours_start:
        return ContactWhen.AFTER_START_TODAY
    if local >= ops.hours_end:
        return ContactWhen.AFTER_START_TOMORROW
    return ContactWhen.TODAY


def reply_by(last_inbound: datetime, window_hours: float) -> datetime:
    return last_inbound + timedelta(hours=window_hours)


def format_ist(at: datetime, timezone: str) -> str:
    return at.astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
