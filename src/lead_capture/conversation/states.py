"""Conversation lifecycle (data-model.md). Only CONFIRMING → COMPLETED creates a lead."""

from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    """Conversation states (data-model.md lifecycle)."""

    AWAITING_CONSENT = "awaiting_consent"
    IN_PROGRESS = "in_progress"
    CONFIRMING = "confirming"
    STALLED = "stalled"
    HANDED_OVER = "handed_over"
    COMPLETED = "completed"
    CLOSED = "closed"


class CloseReason(StrEnum):
    """Why a conversation was closed without a lead."""

    DECLINED_CONSENT = "declined_consent"
    NOT_INTERESTED = "not_interested"
    OUT_OF_AREA = "out_of_area"
    OPTED_OUT = "opted_out"
    DELETION_REQUEST = "deletion_request"


_ALLOWED: dict[State, set[State]] = {
    State.AWAITING_CONSENT: {State.IN_PROGRESS, State.CLOSED, State.HANDED_OVER, State.STALLED},
    State.IN_PROGRESS: {State.CONFIRMING, State.STALLED, State.HANDED_OVER, State.CLOSED},
    State.CONFIRMING: {
        State.COMPLETED,
        State.IN_PROGRESS,
        State.STALLED,
        State.HANDED_OVER,
        State.CLOSED,
    },
    State.STALLED: {
        State.AWAITING_CONSENT,
        State.IN_PROGRESS,
        State.CONFIRMING,
        State.HANDED_OVER,
        State.CLOSED,
    },
    State.HANDED_OVER: {
        State.AWAITING_CONSENT,
        State.IN_PROGRESS,
        State.CONFIRMING,
        State.COMPLETED,
        State.CLOSED,
    },
    State.COMPLETED: set(),
    State.CLOSED: set(),
}


class InvalidTransition(ValueError):
    """A state change the lifecycle does not allow (a bug, never user input)."""

    pass


def can_transition(frm: str, to: str) -> bool:
    """Whether the lifecycle allows moving from ``frm`` to ``to``."""
    return State(to) in _ALLOWED[State(frm)]


def transition(conv, to: State, reason: CloseReason | None = None) -> None:
    """Move ``conv`` (anything with .state / .close_reason) to ``to``, enforcing the lifecycle."""
    if not can_transition(conv.state, to):
        raise InvalidTransition(f"{conv.state} -> {to}")
    conv.state = str(to)
    if to == State.CLOSED:
        conv.close_reason = str(reason) if reason else None


def creates_lead(frm: str, to: str) -> bool:
    """Only CONFIRMING → COMPLETED creates a lead (constitution Principle II)."""
    return State(frm) == State.CONFIRMING and State(to) == State.COMPLETED
