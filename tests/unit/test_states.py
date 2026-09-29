from types import SimpleNamespace

import pytest

from lead_capture.conversation.states import (
    CloseReason,
    InvalidTransition,
    State,
    creates_lead,
    transition,
)


def conv(state):
    return SimpleNamespace(state=str(state), close_reason=None)


def test_happy_path():
    c = conv(State.AWAITING_CONSENT)
    for to in (State.IN_PROGRESS, State.CONFIRMING, State.COMPLETED):
        transition(c, to)
    assert c.state == "completed"


def test_correction_goes_back_to_in_progress():
    c = conv(State.CONFIRMING)
    transition(c, State.IN_PROGRESS)
    assert c.state == "in_progress"


def test_only_confirming_to_completed_creates_lead():
    assert creates_lead("confirming", "completed")
    assert not creates_lead("in_progress", "confirming")
    with pytest.raises(InvalidTransition):
        transition(conv(State.IN_PROGRESS), State.COMPLETED)


def test_terminal_states_and_close_reason():
    c = conv(State.IN_PROGRESS)
    transition(c, State.CLOSED, CloseReason.OUT_OF_AREA)
    assert c.close_reason == "out_of_area"
    with pytest.raises(InvalidTransition):
        transition(c, State.IN_PROGRESS)
