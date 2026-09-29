"""Clock port — current time in the configured time zone."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware current time (ops.timezone)."""
