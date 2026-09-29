"""Consumes the TurnQueue: debounces bursts into one turn, holds the per-contact lock, applies
turn limits (FR-030), then runs the engine."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from lead_capture.conversation import fixed_texts as ft
from lead_capture.conversation import rate_limit
from lead_capture.conversation.engine import Engine
from lead_capture.ports.channel import InboundMessage, OutboundMessage
from lead_capture.services import Services
from lead_capture.store import queries

log = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, services: Services, engine: Engine) -> None:
        self.sv = services
        self.engine = engine
        self._buffers: defaultdict[str, list[InboundMessage]] = defaultdict(list)
        self._tasks: set[asyncio.Task] = set()
        self._scheduled: set[str] = set()

    def start(self) -> None:
        self.sv.queue.start(self.accept)

    async def accept(self, key: str, item: InboundMessage) -> None:
        self._buffers[key].append(item)
        if key in self._scheduled:
            return
        self._scheduled.add(key)
        task = asyncio.create_task(self._flush_later(key))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _flush_later(self, key: str) -> None:
        await asyncio.sleep(self.sv.settings.conversation.debounce_ms / 1000)
        self._scheduled.discard(key)
        items = self._buffers.pop(key, [])
        if not items:
            return
        async with self.sv.lock.hold(key):
            try:
                if await self._limited(key):
                    return
                await self.engine.run_turn(key, items)
            except Exception:  # noqa: BLE001 - one failed turn must not stop others
                log.exception("turn_failed")

    async def _limited(self, key: str) -> bool:
        with self.sv.sessions() as db:
            contact = queries.get_or_create_contact(db, key)
            verdict = rate_limit.check(
                db, contact, self.sv.clock.now(), self.sv.settings.conversation
            )
            db.commit()
            lang = contact.language or "en"
        if verdict == rate_limit.Verdict.NOTIFY:
            await self.sv.channel.send(key, OutboundMessage(text=ft.text("RATE_LIMITED", lang)))
        return verdict != rate_limit.Verdict.OK

    async def drain(self) -> None:
        """Wait for queued items and pending turns (tests, shutdown)."""
        while True:
            await self.sv.queue.drain()
            pending = [t for t in self._tasks if not t.done()]
            if not pending and not self._buffers:
                return
            await asyncio.gather(*pending, return_exceptions=True)
