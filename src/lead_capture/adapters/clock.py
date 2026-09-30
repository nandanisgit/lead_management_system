"""System and frozen clocks in the configured time zone."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class SystemClock:
    """Real time in the operations time zone."""

    def __init__(self, timezone: str) -> None:
        """Clock in ``timezone`` (ops.timezone)."""
        self.tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        """Current timezone-aware time."""
        return datetime.now(self.tz)


class FrozenClock:
    """Clock tests control: set or advance time to test hours, windows and retention."""

    def __init__(self, at: datetime, timezone: str = "Asia/Kolkata") -> None:
        """Start frozen at ``at`` (naive times are taken as ``timezone``)."""
        self.tz = ZoneInfo(timezone)
        self._now = at if at.tzinfo else at.replace(tzinfo=self.tz)

    def now(self) -> datetime:
        """The frozen time."""
        return self._now

    def set(self, at: datetime) -> None:
        """Jump to a given time (naive times are taken as the configured zone)."""
        self._now = at if at.tzinfo else at.replace(tzinfo=self.tz)

    def advance(self, **delta: float) -> None:
        """Move time forward by ``timedelta`` keyword arguments."""
        self._now += timedelta(**delta)
