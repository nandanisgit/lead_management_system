"""APScheduler setup (research R9). Time zone and intervals from settings; jobs are idempotent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from lead_capture.jobs.outbox import drain_once
from lead_capture.services import Services

log = logging.getLogger(__name__)


def _in_thread(fn: Callable[[Services], object], services: Services):
    """Wrap a blocking job so it runs in a worker thread and never crashes the scheduler."""

    async def run() -> None:
        """Run the job in the default executor; log (not raise) failures."""
        try:
            await asyncio.get_running_loop().run_in_executor(None, fn, services)
        except Exception:  # noqa: BLE001
            log.exception("job_failed", extra={"job": fn.__name__})

    run.__name__ = fn.__name__
    return run


def build_scheduler(services: Services) -> AsyncIOScheduler:
    """Scheduler with the outbox job; interval and time zone come from settings."""
    s = services.settings
    scheduler = AsyncIOScheduler(timezone=s.ops.timezone)
    scheduler.add_job(
        _in_thread(drain_once, services),
        "interval",
        seconds=s.leads.outbox_interval_seconds,
        id="outbox",
        coalesce=True,
        max_instances=1,
    )
    return scheduler
