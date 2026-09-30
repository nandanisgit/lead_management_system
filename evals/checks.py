"""Deterministic eval checks mapped to the spec's success criteria (research R10).

Why: model output varies run to run, so conversation quality is judged by repeatable checks
on the outcome — was the right lead recorded, was anything asked twice, was a budget ever
suggested — rather than by exact wording. Column positions come from the schema.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from lead_capture.conversation import guards
from lead_capture.domain.schema import RequirementSchema
from lead_capture.settings import ConversationSettings


@dataclass
class RunResult:
    """One simulated conversation and its check results."""

    scenario: str
    outcome: str
    bot_messages: list[str]
    tutee_messages: list[str]
    lead_row: list | None
    asked_by_turn: list[tuple[list[str], list[str]]]
    tokens: dict = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _norm(value) -> str:
    """Case/space/underscore-insensitive form for comparing expected and recorded values."""
    return re.sub(r"\s+", " ", str(value)).strip().lower().replace("_", " ")


def _field_columns(schema: RequirementSchema) -> dict[str, int]:
    """Field name → Leads column index, from the configured sheet layout."""
    layout = schema.leads_layout()
    return {
        col.value.partition(".")[2]: layout.index(col.header)
        for col in schema.sheet.leads.columns
        if col.value and col.value.startswith("field.")
    }


def _expected(facts: dict) -> dict:
    """Scenario facts with the budget shorthand ({min, max, unit}) expanded to fields."""
    out = dict(facts)
    if "budget" in out:
        b = out.pop("budget")
        out.setdefault("budget_min", b.get("min"))
        out.setdefault("budget_max", b.get("max", b.get("min")))
        out.setdefault("budget_unit", b.get("unit"))
    return out


def lead_matches_facts(row: list, facts: dict, schema: RequirementSchema, notes: list[str]) -> bool:
    """SC-001: every stated fact is in the recorded lead.

    Choice-like fields must match exactly; free text only needs to contain (or be contained
    in) the stated fact.
    """
    ok = True
    columns = _field_columns(schema)
    for key, want in _expected(facts).items():
        if key not in columns or want is None:
            continue
        got = row[columns[key]]
        spec = schema.fields[key]
        if spec.type == "multi_choice":
            match = {_norm(v) for v in want} == {_norm(v) for v in str(got).split(",")}
        elif spec.type == "text":
            match = _norm(want) in _norm(got) or _norm(got) in _norm(want)
        else:
            match = _norm(want) == _norm(got)
        if not match:
            ok = False
            notes.append(f"{key}: expected {want!r}, got {got!r}")
    return ok


def no_reask(asked_by_turn: list[tuple[list[str], list[str]]], notes: list[str]) -> bool:
    """SC-003: a field is re-asked if a reply requested it while it was already captured."""
    for fields, captured in asked_by_turn:
        again = set(fields) & set(captured)
        if again:
            notes.append(f"re-asked: {sorted(again)}")
            return False
    return True


def message_rules(result: RunResult, lang: str, limits: ConversationSettings) -> bool:
    """FR-001/002: every bot message (except the code-built summary) obeys the guards."""
    ok = True
    for text in result.bot_messages:
        if "•" in text:  # the code-built summary: exempt from the length rule
            continue
        issues = [
            p
            for p in guards.problems(
                text, tutee_texts=result.tutee_messages, language=lang, limits=limits
            )
        ]
        if issues:
            ok = False
            result.notes.append(f"{issues}: {text[:60]}…")
    return ok


def no_amount_suggested(result: RunResult, limits: ConversationSettings) -> bool:
    """SC-003 / FR-006: the bot never introduced a fee or budget amount."""
    for text in result.bot_messages:
        issues = guards.problems(
            text, tutee_texts=result.tutee_messages, language="any", limits=limits
        )
        if "suggested_amount" in issues and "•" not in text:
            result.notes.append(f"amount suggested: {text[:60]}…")
            return False
    return True


def score(
    result: RunResult, scenario: dict, limits: ConversationSettings, schema: RequirementSchema
) -> None:
    """Fill ``result.checks`` for one run; each check maps to a spec criterion."""
    expect = scenario.get("expect", {})
    lang = scenario.get("language", "en")
    result.checks["outcome"] = result.outcome == expect.get("outcome", "lead_recorded")
    if result.checks["outcome"] and result.outcome == "lead_recorded" and result.lead_row:
        result.checks["fields_match (SC-001)"] = lead_matches_facts(
            result.lead_row, scenario["tutee_facts"], schema, result.notes
        )
    result.checks["no_reask (SC-003)"] = no_reask(result.asked_by_turn, result.notes)
    result.checks["no_amount (SC-003)"] = no_amount_suggested(result, limits)
    result.checks["message_rules (FR-001/002)"] = message_rules(result, lang, limits)
    for text in expect.get("bot_says_any", []):
        found = any(text.lower() in m.lower() for m in result.bot_messages)
        result.checks[f"says '{text}'"] = found
    if "lead_notes_start" in expect and result.lead_row:
        result.checks["lead_notes"] = str(result.lead_row[21]).startswith(
            expect["lead_notes_start"]
        )


def median_bot_messages(results: list[RunResult]) -> float:
    """SC-002: median number of bot messages in conversations that recorded a lead."""
    counts = [len(r.bot_messages) for r in results if r.outcome == "lead_recorded"]
    return statistics.median(counts) if counts else 0.0
