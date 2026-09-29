from datetime import date

from lead_capture.conversation.planner import next_fields, plan
from lead_capture.domain.lists import load_lists
from lead_capture.domain.requirement import RequirementState
from lead_capture.ports.llm import Signals

LISTS = load_lists()


def state(**fields):
    s, _ = RequirementState().apply(fields, LISTS, date(2026, 9, 29))
    return s


def test_order_and_grouping():
    s = state()
    assert plan(s, minor_alone=False, rejected={}, signals=None, max_questions=2).params[
        "fields"
    ] == ["contact_name", "relationship"]
    s = state(contact_name="Priya", relationship="parent", student_name="Aarav")
    assert next_fields(s.missing_required(), 2) == ["grade_level", "board"]
    s = state(
        contact_name="Priya",
        relationship="parent",
        student_name="Aarav",
        grade_level="Class 8",
        board="CBSE",
        subjects=["Maths"],
    )
    assert next_fields(s.missing_required(), 2) == ["mode"]


def test_respects_max_questions():
    assert next_fields(["grade_level", "board"], 1) == ["grade_level"]


def test_complete_state_summarises():
    s = state(
        contact_name="Priya",
        relationship="parent",
        student_name="Aarav",
        grade_level="Class 8",
        board="CBSE",
        subjects=["Maths"],
        mode="online",
        schedule="weekday evenings",
        start_date="ASAP",
        budget_min=500,
        budget_unit="per_hour",
    )
    assert plan(s, minor_alone=False, rejected={}, signals=None, max_questions=2).kind == (
        "SUMMARISE_AND_CONFIRM"
    )


def test_guardian_only_for_minors_and_strict_flag():
    s = state(
        contact_name="Aarav",
        relationship="student",
        grade_level="Class 9",
        board="CBSE",
        subjects=["Maths"],
        mode="online",
        schedule="evenings",
        start_date="ASAP",
        budget_min=500,
        budget_unit="per_hour",
    )
    ins = plan(s, minor_alone=True, rejected={}, signals=None, max_questions=2)
    assert ins.params["fields"] == ["guardian_name", "guardian_relationship"] and ins.strict


def test_off_topic_and_fees_instructions():
    s = state()
    fees = plan(
        s,
        minor_alone=False,
        rejected={},
        signals=Signals(asks_fees_or_tutors=True),
        max_questions=2,
    )
    assert fees.kind == "FEES_OR_TUTORS_AND_STEER" and fees.params["fields"]
    off = plan(s, minor_alone=False, rejected={}, signals=Signals(off_topic=True), max_questions=2)
    assert off.kind == "ANSWER_OFF_TOPIC_AND_STEER"
    strict = plan(
        s, minor_alone=True, rejected={}, signals=Signals(off_topic=True), max_questions=2
    )
    assert strict.kind == "STRICT_REDIRECT"


def test_rejected_values_are_clarified():
    s = state()
    ins = plan(
        s, minor_alone=False, rejected={"grade_level": "unknown"}, signals=None, max_questions=2
    )
    assert ins.params["clarify"] == ["grade_level"]
