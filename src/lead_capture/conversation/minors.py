"""FR-029: a minor chatting without a parent."""

from __future__ import annotations

from lead_capture.domain.lists import AllowedLists
from lead_capture.domain.requirement import RequirementState
from lead_capture.ports.llm import Signals


def update_minor_flags(conv, state: RequirementState, signals: Signals | None, lists: AllowedLists):
    """Set minor_alone once detected. Detection always happens after consent, so the consent on
    record was given by the student (consent_by_minor)."""
    if conv.minor_alone:
        return
    if state.relationship == "parent":
        return
    if state.is_minor_alone(lists) or (signals is not None and signals.likely_minor_alone):
        conv.minor_alone = True
        conv.consent_by_minor = True
