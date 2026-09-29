"""Decides what this turn's reply must do (the model only phrases it).

Missing-field order (data-model.md): consent → contact_name & relationship → student_name →
grade_level & board → subjects → mode → area & city → schedule → start_date → budget →
guardian (only if minor_alone) → summary. Optional fields are not asked in v1 (spec A2):
they are recorded whenever the tutee volunteers them.
"""

from __future__ import annotations

from lead_capture.domain.requirement import OUT_OF_AREA, RequirementState
from lead_capture.ports.llm import Instruction, Signals

GROUPS: tuple[tuple[str, ...], ...] = (
    ("contact_name", "relationship"),
    ("student_name",),
    ("grade_level", "board"),
    ("subjects",),
    ("mode",),
    ("area", "city"),
    ("schedule",),
    ("start_date",),
    ("budget_min", "budget_unit"),
    ("guardian_name", "guardian_relationship"),
)


def next_fields(missing: list[str], max_questions: int) -> list[str]:
    for group in GROUPS:
        fields = [f for f in group if f in missing]
        if fields:
            return fields[:max_questions]
    return missing[:max_questions]


def plan(
    state: RequirementState,
    *,
    minor_alone: bool,
    rejected: dict[str, str],
    signals: Signals | None,
    max_questions: int,
) -> Instruction:
    missing = state.missing_required(minor_alone=minor_alone)
    if not missing:
        return Instruction(kind="SUMMARISE_AND_CONFIRM", strict=minor_alone)

    fields = next_fields(missing, max_questions)
    clarify = [f for f, reason in rejected.items() if reason != OUT_OF_AREA]
    ask = Instruction(
        kind="ASK",
        params={"fields": fields, "clarify": clarify},
        strict=minor_alone,
    )
    if signals is None:
        return ask
    if signals.asks_fees_or_tutors:
        return Instruction(kind="FEES_OR_TUTORS_AND_STEER", params=ask.params, strict=minor_alone)
    if signals.off_topic:
        kind = "STRICT_REDIRECT" if minor_alone else "ANSWER_OFF_TOPIC_AND_STEER"
        return Instruction(kind=kind, params=ask.params, strict=minor_alone)
    return ask
