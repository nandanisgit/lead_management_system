"""TurnQueue port — per-contact ordered delivery of turns (in-process now, Redis/SQS later)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

Handler = Callable[[str, Any], Awaitable[None]]


@runtime_checkable
class TurnQueue(Protocol):
    def start(self, handler: Handler) -> None:
        """Begin delivering items; items for one key are handled one at a time, in order."""

    async def put(self, key: str, item: Any) -> None: ...

    async def drain(self) -> None:
        """Wait until every queued item has been handled (tests, shutdown)."""
