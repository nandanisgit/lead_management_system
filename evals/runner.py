"""Eval runner: real engine + real model vs a simulated tutee; fake WhatsApp, in-memory sheet.

Usage: uv run lead-capture eval [--scenario NAME] [--pr-subset] [--model M] [--repeats N]
Exit code 0 when every check's pass rate ≥ evals.pass_threshold, else 1 (2 = not runnable).
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml

from evals.checks import RunResult, median_bot_messages, score
from evals.tutee import SimulatedTutee
from lead_capture.adapters.channels.fake import FakeChannel
from lead_capture.adapters.clock import FrozenClock
from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
from lead_capture.conversation.engine import Engine
from lead_capture.conversation.inbound import handle_inbound
from lead_capture.jobs.outbox import drain_once
from lead_capture.ports.channel import InboundMessage
from lead_capture.registry import build_llm
from lead_capture.services import build_services
from lead_capture.settings import Secrets, load_settings
from lead_capture.store import queries
from lead_capture.store.db import Base, make_engine, make_session_factory
from lead_capture.store.models import Conversation

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenarios"
REPORTS = ROOT / "reports"
MAX_TURNS = 20


class RecordingLLM:
    """Wraps the real LLMClient to record what each reply was asked to request."""

    def __init__(self, inner):
        self.inner = inner
        self.asked: list[tuple[list[str], list[str]]] = []
        self.usage: defaultdict[str, int] = defaultdict(int)

    def _add(self, usage):
        if usage:
            for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
                self.usage[f"{usage.model}:{k}"] += getattr(usage, k)

    async def extract(self, turn):
        result = await self.inner.extract(turn)
        self._add(result.usage)
        return result

    async def write_reply(self, turn, instruction):
        self.asked.append((instruction.params.get("fields", []), list(turn.state)))
        result = await self.inner.write_reply(turn, instruction)
        self._add(result.usage)
        return result


def load_scenarios(name: str | None, pr_subset: bool, subset: list[str]) -> list[dict]:
    out = []
    for f in sorted(SCENARIOS.glob("*.yaml")):
        sc = yaml.safe_load(f.read_text())
        sc.setdefault("name", f.stem)
        if name and sc["name"] != name:
            continue
        if pr_subset and subset and sc["name"] not in subset:
            continue
        out.append(sc)
    return out


def _outcome(conv: Conversation | None) -> str:
    if conv is None:
        return "no_conversation"
    if conv.state == "completed":
        return "lead_recorded"
    if conv.state == "closed":
        return f"closed_{conv.close_reason}"
    if conv.state == "handed_over":
        return "handed_over"
    return f"unfinished_{conv.state}"


async def run_one(scenario: dict, settings, secrets) -> RunResult:
    db = make_engine("sqlite://")
    Base.metadata.create_all(db)
    channel, leads = FakeChannel(), InMemoryLeadRepository()
    llm = RecordingLLM(build_llm(settings, secrets))
    clock = FrozenClock(datetime.now().replace(hour=15, minute=0), settings.ops.timezone)
    sv = build_services(
        settings,
        secrets,
        llm=llm,
        channel=channel,
        leads=leads,
        clock=clock,
        sessions=make_session_factory(db),
    )
    engine = Engine(sv, on_lead_created=lambda: drain_once(sv))
    tutee = SimulatedTutee(
        settings.evals.tutee_model,
        scenario["tutee_facts"],
        scenario.get("style", "plain English, short replies"),
        scenario.get("tutee_extra", ""),
    )
    number = "+919000000001"
    transcript: list[tuple[str, str]] = []
    scripted = list(scenario.get("script", []))
    next_text = scenario["opening"]
    for n in range(MAX_TURNS):
        choice = None
        if next_text.startswith("#"):
            choice, next_text = next_text[1:].strip(), None
        msg = InboundMessage(
            id=f"eval-{n}",
            contact=number,
            type="interactive" if choice else "text",
            text=next_text,
            choice_id=choice,
            timestamp=clock.now(),
        )
        transcript.append(("tutee", f"#{choice}" if choice else next_text or ""))
        before = len(channel.sent)
        await handle_inbound(sv, [msg])
        await engine.run_turn(number, [msg])
        for _, out in channel.sent[before:]:
            options = " ".join(f"[#{c.id}] {c.title}" for c in out.choices)
            transcript.append(("assistant", f"{out.text}\n{options}".strip()))
        with sv.sessions() as s:
            contact = queries.get_or_create_contact(s, number)
            conv = queries.latest_conversation(s, contact.id)
            outcome = _outcome(conv)
        if outcome == "lead_recorded" or outcome.startswith("closed") or outcome == "handed_over":
            break
        clock.advance(seconds=30)
        next_text = scripted.pop(0) if scripted else tutee.reply(transcript)
    result = RunResult(
        scenario=scenario["name"],
        outcome=outcome,
        bot_messages=[t for r, t in transcript if r == "assistant"],
        tutee_messages=[t for r, t in transcript if r == "tutee"],
        lead_row=leads.leads[0] if leads.leads else None,
        asked_by_turn=llm.asked,
        tokens={**llm.usage, **{f"tutee:{k}": v for k, v in tutee.usage.items()}},
    )
    score(result, scenario, settings.conversation)
    return result


def write_report(results: list[RunResult], settings, threshold: float) -> tuple[Path, bool]:
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"{datetime.now():%Y-%m-%d-%H%M%S}.md"
    rates: defaultdict[str, list[bool]] = defaultdict(list)
    for r in results:
        for check, ok in r.checks.items():
            rates[check].append(ok)
    median = median_bot_messages(results)
    lines = ["# Eval report", "", f"Runs: {len(results)}", ""]
    lines += ["| Check | Pass rate |", "|---|---|"]
    passed = True
    for check, oks in sorted(rates.items()):
        rate = sum(oks) / len(oks)
        passed &= rate >= threshold
        lines.append(f"| {check} | {rate:.0%} ({sum(oks)}/{len(oks)}) |")
    sc002 = median <= 8
    passed &= sc002
    lines.append(f"| median bot messages ≤ 8 (SC-002) | {median} {'✅' if sc002 else '❌'} |")
    lines += ["", f"Threshold: {threshold:.0%} per check. Overall: {'PASS' if passed else 'FAIL'}"]
    lines += ["", "## Runs", ""]
    for r in results:
        failed = [c for c, ok in r.checks.items() if not ok]
        lines.append(
            f"- **{r.scenario}** → {r.outcome}; {len(r.bot_messages)} bot messages; "
            f"failed: {failed or 'none'}"
        )
        lines += [f"  - {note}" for note in r.notes]
    lines += ["", "## Tokens", "", "```", json.dumps(_sum_tokens(results), indent=1), "```"]
    lines += [
        "",
        "## Effective settings",
        "",
        "```json",
        json.dumps(settings.effective(), indent=1),
        "```",
    ]
    path.write_text("\n".join(lines))
    return path, passed


def _sum_tokens(results):
    total: defaultdict[str, int] = defaultdict(int)
    for r in results:
        for k, v in r.tokens.items():
            total[k] += v
    return dict(total)


def run(scenario=None, pr_subset=False, model=None, repeats=None) -> int:
    secrets = Secrets()
    if not (secrets.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")):
        print("ANTHROPIC_API_KEY is not set — evals need the real model.")
        return 2
    over = {"llm": {"provider": "anthropic"}}
    if model:
        over["llm"]["reply_model"] = model
    settings = load_settings(**over)
    scenarios = load_scenarios(scenario, pr_subset, settings.evals.pr_subset)
    if not scenarios:
        print("no matching scenarios")
        return 2
    n = 1 if pr_subset else (repeats or settings.evals.repeats)
    results = [asyncio.run(run_one(sc, settings, secrets)) for sc in scenarios for _ in range(n)]
    path, passed = write_report(results, settings, settings.evals.pass_threshold)
    print(path.read_text().split("## Runs")[0])
    print(f"report: {path}")
    return 0 if passed else 1
