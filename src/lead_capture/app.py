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
    log.info("inbound_ignored", extra={"count": len(messages)})


def create_app(
    services: Services, inbound_handler: InboundHandler | None = None, check_sheet: bool = True
) -> FastAPI:
    handler = inbound_handler or _noop_inbound

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if check_sheet:
            try:
                services.leads.check_headers()
            except RepositoryContractError:
                log.error("sheet_header_mismatch")
                raise
        yield

    app = FastAPI(title="lead-capture", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.services = services

    def _channel(name: str):
        if name != services.channel.name and not (
            name == "whatsapp" and services.channel.name == "whatsapp_cloud"
        ):
            raise HTTPException(status_code=404)
        return services.channel

    @app.get("/webhooks/{channel_name}")
    async def verify(channel_name: str, request: Request) -> Response:
        challenge = _channel(channel_name).verify_subscription(dict(request.query_params))
        if challenge is None:
            raise HTTPException(status_code=403)
        return PlainTextResponse(challenge)

    @app.post("/webhooks/{channel_name}")
    async def receive(channel_name: str, request: Request) -> Response:
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
