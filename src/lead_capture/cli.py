"""lead-capture CLI (Typer).

Why: everything outside the chat apps — local chats, evals, load tests, cost reports, sheet setup,
replaying webhooks and running jobs by hand — is one command away, for people, CI and coding
agents alike (see CLAUDE.md → Commands).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import UTC, datetime
from pathlib import Path

import typer

app = typer.Typer(help="lead-capture: WhatsApp/Telegram tutor-lead capture", no_args_is_help=True)
jobs_app = typer.Typer(help="Run a scheduled job by hand")
app.add_typer(jobs_app, name="jobs")


def _todo(name: str) -> None:
    """Placeholder for commands delivered in later tasks; exits with status 1."""
    typer.echo(f"{name}: not implemented yet")
    raise typer.Exit(code=1)


def _project_root_on_path() -> None:
    """evals/ and load/ live beside src/ (test tooling, not part of the package)."""
    import sys

    from lead_capture.settings import ROOT

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _services(**over):
    """Services from settings and environment, with optional overrides."""
    from lead_capture.services import build_services
    from lead_capture.settings import Secrets, get_settings

    return build_services(get_settings(), Secrets(), **over)


@app.command()
def chat(
    number: str = "+919999900001",
    sheet: bool = typer.Option(False, help="Write confirmed leads to the real Google Sheet"),
) -> None:
    """Chat with the real engine in the terminal (fake WhatsApp).

    Type ``#<option id>`` (e.g. ``#mode:home``) to tap an option, ``/quit`` to exit.
    """
    from lead_capture.adapters.channels.fake import FakeChannel
    from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
    from lead_capture.conversation.engine import Engine
    from lead_capture.conversation.inbound import handle_inbound
    from lead_capture.jobs.outbox import drain_once
    from lead_capture.ports.channel import InboundMessage
    from lead_capture.store.db import Base, make_engine, make_session_factory

    engine_db = make_engine("sqlite://")
    Base.metadata.create_all(engine_db)
    over = {"channel": FakeChannel(), "sessions": make_session_factory(engine_db)}
    sv = _services(**over)
    if not sheet:
        sv.leads = InMemoryLeadRepository(
            sv.schema.leads_layout(), sv.schema.handoffs_layout(), timezone=sv.settings.ops.timezone
        )
    engine = Engine(sv, on_lead_created=lambda: drain_once(sv))

    async def loop() -> None:
        """Read lines from the terminal until /quit and print the bot's replies."""
        n = 0
        while True:
            line = typer.prompt("you", default="", show_default=False)
            if line.strip() == "/quit":
                return
            n += 1
            choice = line[1:].strip() if line.startswith("#") else None
            msg = InboundMessage(
                id=f"chat-{n}",
                contact=number,
                type="interactive" if choice else "text",
                text=None if choice else line,
                choice_id=choice,
                timestamp=datetime.now(UTC),
            )
            before = len(sv.channel.sent)
            await handle_inbound_direct(msg)
            for _, out in sv.channel.sent[before:]:
                typer.secho(f"bot: {out.text}", fg="green")
                for c in out.choices:
                    typer.secho(f"     [#{c.id}] {c.title}", fg="cyan")
            if isinstance(sv.leads, InMemoryLeadRepository) and sv.leads.leads:
                typer.secho(f"(lead rows: {len(sv.leads.leads)})", fg="yellow")

    async def handle_inbound_direct(msg: InboundMessage) -> None:
        """Store the message and run the turn immediately (no queue/debounce in the CLI)."""

        class _DirectQueue:
            """Queue stand-in that runs the turn at once."""

            async def put(self, key, item):
                """Run the turn for ``item`` now."""
                await engine.run_turn(key, [item])

        sv.queue = _DirectQueue()  # type: ignore[assignment]
        await handle_inbound(sv, [msg])

    asyncio.run(loop())


@app.command("eval")
def eval_(
    scenario: str | None = None,
    pr_subset: bool = False,
    model: str | None = None,
    repeats: int | None = None,
    provider: str | None = typer.Option(
        None, help="anthropic | ollama (default: llm.provider in settings)"
    ),
) -> None:
    """Run conversation evals against a real model (simulated tutee)."""
    _project_root_on_path()
    from evals.runner import run

    raise typer.Exit(
        code=run(
            scenario=scenario, pr_subset=pr_subset, model=model, repeats=repeats, provider=provider
        )
    )


@app.command()
def load(profile: str = typer.Option(..., help="capacity | burst | soak")) -> None:
    """Run a load-test profile."""
    _todo("load")


@app.command()
def costs(month: str = typer.Option(..., help="YYYY-MM")) -> None:
    """Summarise messages, tokens and estimated cost per conversation and per lead."""
    _todo("costs")


@app.command("check-sheet")
def check_sheet() -> None:
    """Check access to the lead sheet and its header contract."""
    from lead_capture import registry
    from lead_capture.domain.schema import get_schema
    from lead_capture.ports.leads import RepositoryContractError, RepositoryUnavailable
    from lead_capture.settings import Secrets, get_settings

    try:
        registry.build_lead_repository(get_settings(), Secrets(), get_schema()).check_headers()
    except (RepositoryContractError, RepositoryUnavailable, OSError) as exc:
        typer.secho(f"sheet check failed: {exc}", fg="red")
        raise typer.Exit(code=1) from None
    typer.secho("sheet ok: tabs and headers match the contract", fg="green")


@app.command("set-webhook")
def set_webhook(
    public_url: str = typer.Argument(
        ..., help="Public HTTPS address of this service, e.g. the cloudflared URL"
    ),
) -> None:
    """Register this service's webhook with the chat app (Telegram).

    WhatsApp's webhook is set in Meta's dashboard instead; for it this prints the URL to use.
    """
    from lead_capture import registry
    from lead_capture.ports.channel import ChannelError, SignatureError
    from lead_capture.settings import Secrets, get_settings

    channel = registry.build_channel(get_settings(), Secrets())
    webhook = f"{public_url.rstrip('/')}/webhooks/{channel.path_name}"
    register = getattr(channel, "register_webhook", None)
    if register is None:
        typer.echo(f"{channel.name}: set this webhook URL in the provider's dashboard: {webhook}")
        raise typer.Exit(code=1)
    if not public_url.startswith("https://"):
        typer.secho("the public URL must start with https://", fg="red")
        raise typer.Exit(code=1)
    try:
        asyncio.run(register(public_url))
    except (ChannelError, SignatureError) as exc:
        typer.secho(f"webhook registration failed: {exc}", fg="red")
        raise typer.Exit(code=1) from None
    typer.secho(f"webhook set: {webhook}", fg="green")


@app.command("sync-lists")
def sync_lists(dry_run: bool = False) -> None:
    """Write config/lists.yaml into the sheet's Lists tab."""
    from lead_capture import registry
    from lead_capture.domain.schema import get_schema
    from lead_capture.settings import Secrets, get_settings

    schema = get_schema()
    lists = schema.lists_tab()
    if dry_run:
        for header, values in lists.items():
            typer.echo(f"{header}: {', '.join(values)}")
        return
    registry.build_lead_repository(get_settings(), Secrets(), schema).sync_lists(lists)
    typer.secho("Lists tab updated", fg="green")


@app.command()
def replay(
    file: Path,
    url: str = "http://localhost:8000/webhooks/whatsapp",
) -> None:
    """Re-send a saved WhatsApp webhook payload (signed with WA_APP_SECRET)."""
    import httpx

    from lead_capture.settings import Secrets

    secret = Secrets().wa_app_secret
    if not secret:
        typer.secho("WA_APP_SECRET is not set", fg="red")
        raise typer.Exit(code=1)
    body = file.read_bytes()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = httpx.post(
        url, content=body, headers={"X-Hub-Signature-256": f"sha256={sig}"}, timeout=10
    )
    typer.echo(f"{resp.status_code}")


@jobs_app.command("run")
def run_job(name: str = typer.Argument(..., help="outbox")) -> None:
    """Run one scheduled job now."""
    if name == "outbox":
        from lead_capture.jobs.outbox import drain_once

        typer.echo(f"synced {drain_once(_services())} lead(s)")
        return
    _todo(f"jobs {name}")
