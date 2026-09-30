"""FR-029: a minor chatting without a parent.

Why: a student under 18 chatting alone needs a stricter conversation and a parent or
guardian contact before the lead is recorded. Detection happens only after consent (the
bot collects nothing before), so the consent on record was given by the student — that is
flagged for the operations team.
"""

from __future__ import annotations

from lead_capture.domain.requirement import Requirement
from lead_capture.domain.schema import RequirementSchema
from lead_capture.ports.llm import Signals


def update_minor_flags(
    conv, req: Requirement, signals: Signals | None, schema: RequirementSchema
) -> None:
    """Set ``conv.minor_alone`` / ``conv.consent_by_minor`` once a minor is detected.

    Detection uses the config rule (``minor_alone_when``) or the model's
    ``likely_minor_alone`` signal; ``never_minor_when`` (e.g. a parent chatting) overrides.
    Once set, the flag stays for the conversation.
    """
    if conv.minor_alone:
        return
    if schema.never_minor_when and schema.evaluate(schema.never_minor_when, req.values, {}):
        return
    if req.is_minor_alone(schema) or (signals is not None and signals.likely_minor_alone):
        conv.minor_alone = True
        conv.consent_by_minor = True
