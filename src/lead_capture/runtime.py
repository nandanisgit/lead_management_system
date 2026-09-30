"""Production wiring: engine + dispatcher + scheduler inside the FastAPI app lifecycle."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from lead_capture.app import create_app
from lead_capture.conversation.dispatcher import Dispatcher
from lead_capture.conversation.engine import Engine
from lead_capture.conversation.inbound import handle_inbound
from lead_capture.jobs.outbox import drain_once
from lead_capture.jobs.scheduler import build_scheduler
from lead_capture.logging import setup_logging
from lead_capture.services import Services, build_services
from lead_capture.settings import Secrets, get_settings

log = logging.getLogger(__name__)


def kick_outbox(services: Services) -> None:
    """Write a just-confirmed lead immediately (the scheduled job is the safety net)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        drain_once(services)
        return
    loop.run_in_executor(None, drain_once, services)


def create_runtime_app(services: Services) -> FastAPI:
    """App with the engine, debounced dispatcher and scheduler started/stopped with it."""
    engine = Engine(services, on_lead_created=lambda: kick_outbox(services))
    dispatcher = Dispatcher(services, engine)
    scheduler = build_scheduler(services)

    async def on_start() -> None:
        """Begin consuming turns and running scheduled jobs."""
        dispatcher.start()
        scheduler.start()

    async def on_stop() -> None:
        """Stop jobs and finish in-flight turns before exit."""
        scheduler.shutdown(wait=False)
        await dispatcher.drain()

    return create_app(services, handle_inbound, on_start=on_start, on_stop=on_stop)


def create_production_app() -> FastAPI:
    """The app uvicorn serves: real adapters from settings, JSON logging without PII."""
    services = build_services(get_settings(), Secrets())
    setup_logging(pii_fields=services.schema.pii_fields())
    return create_runtime_app(services)


class LazyApp:
    """ASGI app built on first use, so importing lead_capture.app needs no secrets."""

    def __init__(self) -> None:
        """Nothing is built until the first request."""
        self._app: FastAPI | None = None

    async def __call__(self, scope, receive, send):
        """ASGI entry point: build the real app on first use, then delegate."""
        if self._app is None:
            self._app = create_production_app()
        await self._app(scope, receive, send)
