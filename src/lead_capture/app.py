"""FastAPI app: /webhooks/{channel} and /healthz. Business logic lives in conversation/."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select, text

from lead_capture.ports.channel import InboundMessage, SignatureError
from lead_capture.ports.leads import RepositoryContractError
from lead_capture.services import Services
from lead_capture.store.models import LeadOutbox

log = logging.getLogger(__name__)

InboundHandler = Callable[[Services, list[InboundMessage]], Awaitable[None]]


async def _noop_inbound(services: Services, messages: list[InboundMessage]) -> None:
    """Default inbound handler for tests of the HTTP layer alone: log and drop."""
    log.info("inbound_ignored", extra={"count": len(messages)})


def create_app(
    services: Services,
    inbound_handler: InboundHandler | None = None,
    check_sheet: bool = True,
    on_start: Callable[[], Awaitable[None]] | None = None,
    on_stop: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    """The FastAPI app: webhook routes per channel and a health check.

    Business logic is injected (``inbound_handler``, ``on_start``/``on_stop``) so the app
    can be tested with fakes and wired for production in ``runtime.py``.
    """
    handler = inbound_handler or _noop_inbound

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Check the sheet layout, then start background work; stop it on shutdown."""
        if check_sheet:
            try:
                services.leads.check_headers()
            except RepositoryContractError:
                log.error("sheet_header_mismatch")
                raise
        if on_start:
            await on_start()
        yield
        if on_stop:
            await on_stop()

    app = FastAPI(title="lead-capture", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.services = services

    def _channel(name: str):
        """The configured channel if this path is its webhook, else 404."""
        if name != services.channel.path_name:
            raise HTTPException(status_code=404)
        return services.channel

    @app.get("/webhooks/{channel_name}")
    async def verify(channel_name: str, request: Request) -> Response:
        """Webhook subscription handshake (GET)."""
        challenge = _channel(channel_name).verify_subscription(dict(request.query_params))
        if challenge is None:
            raise HTTPException(status_code=403)
        return PlainTextResponse(challenge)

    @app.post("/webhooks/{channel_name}")
    async def receive(channel_name: str, request: Request) -> Response:
        """Webhook events (POST): verify, store, queue, and answer 200 fast."""
        channel = _channel(channel_name)
        body = await request.body()
        try:
            messages = channel.parse_inbound(dict(request.headers), body)
        except SignatureError:
            raise HTTPException(status_code=401) from None
        await handler(services, messages)  # stores + enqueues; must return fast
        return Response(status_code=200)

    @app.get("/healthz")
    async def healthz() -> dict:
        """Liveness and outbox backlog for monitoring — no personal data."""
        db_ok = "ok"
        pending = 0
        try:
            with services.sessions() as s:
                s.execute(text("SELECT 1"))
                pending = s.scalar(
                    select(func.count())
                    .select_from(LeadOutbox)
                    .where(LeadOutbox.status == "pending")
                )
        except Exception:  # noqa: BLE001
            db_ok = "error"
        return {
            "status": "ok" if db_ok == "ok" else "degraded",
            "db": db_ok,
            "outbox_pending": pending,
        }

    return app


def __getattr__(name: str):
    """``uvicorn lead_capture.app:app`` — built lazily on first request (see runtime.LazyApp)."""
    if name == "app":
        from lead_capture.runtime import LazyApp

        return LazyApp()
    raise AttributeError(name)
