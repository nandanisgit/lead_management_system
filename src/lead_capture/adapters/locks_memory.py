"""In-memory per-contact lock (single process)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class InMemoryConversationLock:
    """ConversationLock for a single process (research R14: shared lock later)."""

    def __init__(self) -> None:
        """One asyncio lock per contact key, created on first use."""
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        """Hold the lock for one contact so two turns for them never overlap."""
        async with self._locks[key]:
            yield
