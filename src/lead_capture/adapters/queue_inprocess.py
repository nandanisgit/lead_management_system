"""In-process TurnQueue: one asyncio worker per active contact key; ordered per key."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from lead_capture.ports.queue import Handler

log = logging.getLogger(__name__)


class InProcessTurnQueue:
    def __init__(self) -> None:
        self._handler: Handler | None = None
        self._queues: dict[str, asyncio.Queue] = {}
        self._workers: dict[str, asyncio.Task] = {}

    def start(self, handler: Handler) -> None:
        self._handler = handler

    async def put(self, key: str, item: Any) -> None:
        if self._handler is None:
            raise RuntimeError("TurnQueue.start() must be called first")
        q = self._queues.setdefault(key, asyncio.Queue())
        await q.put(item)
        worker = self._workers.get(key)
        if worker is None or worker.done():
            self._workers[key] = asyncio.create_task(self._run(key, q))

    async def _run(self, key: str, q: asyncio.Queue) -> None:
        assert self._handler is not None
        while not q.empty():
            item = await q.get()
            try:
                await self._handler(key, item)
            except Exception:  # noqa: BLE001 - one bad turn must not stop the worker
                log.exception("turn_failed", extra={"contact_key": key})
            finally:
                q.task_done()

    async def drain(self) -> None:
        while True:
            pending = [t for t in self._workers.values() if not t.done()]
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)
