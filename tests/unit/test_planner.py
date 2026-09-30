from datetime import date

from lead_capture.conversation.planner import next_fields, plan
from lead_capture.domain.requirement import Requirement
from lead_capture.ports.llm import Signals


def req(schema, **fields):
    r, _ = Requirement().apply(fields, schema, date(2026, 9, 29))
    return r


def ask(schema, r, **kw):
    kw.setdefault("minor_alone", False)
    kw.setdefault("rejected", {})
    kw.setdefault("signals", None)
    return plan(r, schema, max_questions=2, **kw)


def test_order_and_grouping(schema):
    assert ask(schema, req(schema)).params["fields"] == ["contact_name", "relationship"]
    r = req(schema, contact_name="Priya", relationship="parent", student_name="Aarav")
    assert next_fields(r.missing_required(schema), schema, 2) == ["grade_level", "board"]
    r = req(
        schema,
        contact_name="Priya",
        relationship="parent",
        student_name="Aarav",
        grade_level="Class 8",
        board="CBSE",
        subjects=["Maths"],
    )
    assert next_fields(r.missing_required(schema), schema, 2) == ["mode"]


def test_respects_max_questions(schema):
    assert next_fields(["grade_level", "board"], schema, 1) == ["grade_level"]


def test_complete_requirement_summarises(schema):
    r = req(
        schema,
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
    assert ask(schema, r).kind == "SUMMARISE_AND_CONFIRM"


def test_guardian_only_for_minors_and_strict_flag(schema):
    r = req(
        schema,
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
    ins = ask(schema, r, minor_alone=True)
    assert ins.params["fields"] == ["guardian_name", "guardian_relationship"] and ins.strict


def test_off_topic_and_fees_instructions(schema):
    r = req(schema)
    fees = ask(schema, r, signals=Signals(asks_fees_or_tutors=True))
    assert fees.kind == "FEES_OR_TUTORS_AND_STEER" and fees.params["fields"]
    assert ask(schema, r, signals=Signals(off_topic=True)).kind == "ANSWER_OFF_TOPIC_AND_STEER"
    strict = ask(schema, r, minor_alone=True, signals=Signals(off_topic=True))
    assert strict.kind == "STRICT_REDIRECT"


def test_rejected_values_are_clarified(schema):
    assert ask(schema, req(schema), rejected={"grade_level": "x"}).params["clarify"] == [
        "grade_level"
    ]
