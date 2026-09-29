"""In-memory per-contact lock (single process)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class InMemoryConversationLock:
    def __init__(self) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        async with self._locks[key]:
            yield
