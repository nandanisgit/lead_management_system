"""System and frozen clocks in the configured time zone."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class SystemClock:
    def __init__(self, timezone: str) -> None:
        self.tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        return datetime.now(self.tz)


class FrozenClock:
    def __init__(self, at: datetime, timezone: str = "Asia/Kolkata") -> None:
        self.tz = ZoneInfo(timezone)
        self._now = at if at.tzinfo else at.replace(tzinfo=self.tz)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = at if at.tzinfo else at.replace(tzinfo=self.tz)

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)
