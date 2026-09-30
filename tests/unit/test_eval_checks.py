"""Eval scoring checks (evals/checks.py)."""

from datetime import date

from evals.checks import RunResult, lead_matches_facts, no_reask, score

from lead_capture.conversation.summary import lead_values
from lead_capture.domain.requirement import Requirement
from lead_capture.domain.schema import get_schema
from lead_capture.settings import load_settings

LIMITS = load_settings().conversation
SCHEMA = get_schema()
FACTS = {
    "contact_name": "Priya",
    "relationship": "parent",
    "student_name": "Aarav",
    "grade_level": "Class 8",
    "board": "CBSE",
    "subjects": ["Science", "Maths"],
    "mode": "home",
    "area": "Dwarka Sector 12",
    "city": "Delhi",
    "schedule": "weekdays after 5 pm",
    "start_date": "ASAP",
    "budget": {"min": 600, "unit": "per_hour"},
}


def row_for(facts):
    fields = {k: v for k, v in facts.items() if k != "budget"}
    fields |= {"budget_min": facts["budget"]["min"], "budget_unit": facts["budget"]["unit"]}
    req, rejected = Requirement().apply(fields, SCHEMA, date(2026, 9, 29))
    assert rejected == {}
    return lead_values(SCHEMA, req, {}, minor_alone=False)


ROW = row_for(FACTS)


def test_lead_matches_facts():
    notes = []
    assert lead_matches_facts(ROW, FACTS, SCHEMA, notes) and notes == []
    assert not lead_matches_facts(ROW, {**FACTS, "board": "ICSE"}, SCHEMA, notes)
    assert "board" in notes[0]


def test_no_reask_detects_asking_for_captured_fields():
    notes = []
    assert no_reask([(["mode"], ["grade_level"])], notes)
    assert not no_reask([(["grade_level"], ["grade_level", "board"])], notes)


def test_score_flags_amounts_and_outcome():
    r = RunResult(
        scenario="x",
        outcome="lead_recorded",
        bot_messages=["Most parents pay ₹500 per hour."],
        tutee_messages=["hi"],
        lead_row=ROW,
        asked_by_turn=[],
    )
    score(r, {"tutee_facts": FACTS, "expect": {"outcome": "lead_recorded"}}, LIMITS, SCHEMA)
    assert r.checks["outcome"] and r.checks["fields_match (SC-001)"]
    assert not r.checks["no_amount (SC-003)"]
