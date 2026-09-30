"""Decides what this turn's reply must do; the model only phrases it.

Why: keeping the decision in code (not the model) makes the conversation predictable and
testable — what to ask next follows the ask groups in config/requirement.yaml, off-topic
and fee questions get a fixed treatment (FR-007), and the summary appears only when
nothing required is missing. Optional fields are recorded when volunteered, never asked.
"""

from __future__ import annotations

from lead_capture.domain.requirement import OUT_OF_AREA, Requirement
from lead_capture.domain.schema import RequirementSchema
from lead_capture.ports.llm import Instruction, Signals


def next_fields(missing: list[str], schema: RequirementSchema, max_questions: int) -> list[str]:
    """The next fields to ask.

    The first ask group with a missing field, capped at ``max_questions`` (FR-001).
    """
    for group in schema.ask_groups:
        fields = [f for f in group.fields if f in missing]
        if fields:
            return fields[:max_questions]
    return missing[:max_questions]


def plan(
    req: Requirement,
    schema: RequirementSchema,
    *,
    minor_alone: bool,
    rejected: dict[str, str],
    signals: Signals | None,
    max_questions: int,
) -> Instruction:
    """Choose this turn's instruction from the captured state and the model's signals.

    ``signals`` is None for deterministic turns (button taps), where no model ran.
    """
    missing = req.missing_required(schema, minor_alone)
    if not missing:
        return Instruction(kind="SUMMARISE_AND_CONFIRM", strict=minor_alone)
    fields = next_fields(missing, schema, max_questions)
    clarify = [f for f, reason in rejected.items() if reason != OUT_OF_AREA]
    params = {"fields": fields, "clarify": clarify}
    if signals is not None and signals.asks_fees_or_tutors:
        return Instruction(kind="FEES_OR_TUTORS_AND_STEER", params=params, strict=minor_alone)
    if signals is not None and signals.off_topic:
        kind = "STRICT_REDIRECT" if minor_alone else "ANSWER_OFF_TOPIC_AND_STEER"
        return Instruction(kind=kind, params=params, strict=minor_alone)
    return Instruction(kind="ASK", params=params, strict=minor_alone)
