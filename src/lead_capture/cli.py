"""lead-capture CLI (Typer). Commands are filled in by the user-story and polish tasks."""

from __future__ import annotations

import typer

app = typer.Typer(help="lead-capture: WhatsApp tutor-lead capture", no_args_is_help=True)
jobs_app = typer.Typer(help="Run a scheduled job by hand")
app.add_typer(jobs_app, name="jobs")


def _todo(name: str) -> None:
    typer.echo(f"{name}: not implemented yet")
    raise typer.Exit(code=1)


@app.command()
def chat(number: str = "+919999900001", sheet: bool = False) -> None:
    """Chat with the real engine in the terminal (fake WhatsApp)."""
    _todo("chat")


@app.command("eval")
def eval_(scenario: str | None = None, pr_subset: bool = False, model: str | None = None) -> None:
    """Run conversation evals against the real model."""
    _todo("eval")


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
    _todo("check-sheet")


@app.command("sync-lists")
def sync_lists(dry_run: bool = False) -> None:
    """Write config/lists.yaml into the sheet's Lists tab."""
    _todo("sync-lists")


@app.command()
def replay(file: str) -> None:
    """Re-send a saved webhook payload to the running service."""
    _todo("replay")


@jobs_app.command("run")
def run_job(
    name: str = typer.Argument(..., help="outbox | stalled | handoffs | retention"),
) -> None:
    """Run one scheduled job now."""
    _todo(f"jobs {name}")
