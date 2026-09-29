"""Deterministic eval checks mapped to the spec's success criteria (research R10)."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from lead_capture.conversation import guards
from lead_capture.settings import ConversationSettings

_LEAD_COLUMNS = {
    "contact_name": 3,
    "relationship": 4,
    "student_name": 5,
    "grade_level": 6,
    "board": 7,
    "subjects": 8,
    "mode": 9,
    "area": 10,
    "city": 11,
    "schedule": 13,
    "start_date": 14,
    "budget_min": 15,
    "budget_max": 16,
    "budget_unit": 17,
}
_EXACT = {
    "relationship",
    "grade_level",
    "board",
    "mode",
    "city",
    "budget_min",
    "budget_max",
    "budget_unit",
    "start_date",
}


@dataclass
class RunResult:
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
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def lead_matches_facts(row: list, facts: dict, notes: list[str]) -> bool:
    ok = True
    expected = dict(facts)
    if "budget" in expected:
        b = expected.pop("budget")
        expected.setdefault("budget_min", b.get("min"))
        expected.setdefault("budget_max", b.get("max", b.get("min")))
        expected.setdefault("budget_unit", b.get("unit", "").replace("_", " "))
    for key, col in _LEAD_COLUMNS.items():
        if key not in expected or expected[key] is None:
            continue
        want, got = expected[key], row[col]
        if key == "subjects":
            match = {_norm(s) for s in want} == {_norm(s) for s in str(got).split(",")}
        elif key in _EXACT:
            match = _norm(want).replace("_", " ") == _norm(got).replace("_", " ")
        else:
            match = _norm(want) in _norm(got) or _norm(got) in _norm(want)
        if not match:
            ok = False
            notes.append(f"{key}: expected {want!r}, got {got!r}")
    return ok


def no_reask(asked_by_turn: list[tuple[list[str], list[str]]], notes: list[str]) -> bool:
    """A field is re-asked if a reply was asked to request it while it was already captured."""
    for fields, captured in asked_by_turn:
        again = set(fields) & set(captured)
        if again:
            notes.append(f"re-asked: {sorted(again)}")
            return False
    return True


def message_rules(result: RunResult, lang: str, limits: ConversationSettings) -> bool:
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
    for text in result.bot_messages:
        issues = guards.problems(
            text, tutee_texts=result.tutee_messages, language="any", limits=limits
        )
        if "suggested_amount" in issues and "•" not in text:
            result.notes.append(f"amount suggested: {text[:60]}…")
            return False
    return True


def score(result: RunResult, scenario: dict, limits: ConversationSettings) -> None:
    expect = scenario.get("expect", {})
    lang = scenario.get("language", "en")
    result.checks["outcome"] = result.outcome == expect.get("outcome", "lead_recorded")
    if result.checks["outcome"] and result.outcome == "lead_recorded" and result.lead_row:
        result.checks["fields_match (SC-001)"] = lead_matches_facts(
            result.lead_row, scenario["tutee_facts"], result.notes
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
    counts = [len(r.bot_messages) for r in results if r.outcome == "lead_recorded"]
    return statistics.median(counts) if counts else 0.0
