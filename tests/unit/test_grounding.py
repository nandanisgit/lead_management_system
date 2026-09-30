"""T151: model-proposed values survive only if the tutee actually said them."""

import pytest

from lead_capture.conversation.grounding import grounded


def keep(schema, texts, **fields):
    kept, _ = grounded(schema, fields, texts if isinstance(texts, list) else [texts])
    return kept


@pytest.mark.parametrize(
    "said,fields,expected",
    [
        # invented details (seen with a small local model) are dropped
        ("hi", {"schedule": "Monday and Wednesday", "start_date": "ASAP"}, {}),
        ("Ramya is in 1 class", {"grade_level": "Class 8"}, {}),
        ("I want offline tuitions", {"mode": "online"}, {}),
        ("700$", {"budget_unit": "per_hour"}, {}),
        ("need a tutor", {"contact_name": "Priya"}, {}),
        # what was said is kept, however it was phrased
        ("Ramya is in 1 class", {"grade_level": "Class 1"}, {"grade_level": "Class 1"}),
        ("Ramya is in first standard", {"grade_level": "Class 1"}, {"grade_level": "Class 1"}),
        ("pehli class mein hai", {"grade_level": "Class 1"}, {"grade_level": "Class 1"}),
        ("she is in 9th", {"grade_level": "Class 9"}, {"grade_level": "Class 9"}),
        ("I want offline tuitions", {"mode": "home"}, {"mode": "home"}),
        ("home tuition please", {"mode": "home"}, {"mode": "home"}),
        ("700$", {"budget_min": 700}, {"budget_min": 700}),
        ("around 6,000 a month", {"budget_min": 6000}, {"budget_min": 6000}),
        ("start asap", {"start_date": "ASAP"}, {"start_date": "ASAP"}),
        ("abhi se", {"start_date": "ASAP"}, {"start_date": "ASAP"}),
        ("for my son", {"relationship": "parent"}, {"relationship": "parent"}),
        ("my mom Sunita", {"guardian_relationship": "mother"}, {"guardian_relationship": "mother"}),
        ("I am Nandani", {"contact_name": "Nandani"}, {"contact_name": "Nandani"}),
        ("NOIDA", {"city": "Noida"}, {"city": "Noida"}),
        ("need math help", {"subjects": ["Maths"]}, {"subjects": ["Maths"]}),
        (
            "weekdays in the evening",
            {"schedule": "weekday evenings"},
            {"schedule": "weekday evenings"},
        ),
        ("This is my 8510916320", {"phone": "+918510916320"}, {"phone": "+918510916320"}),
    ],
)
def test_grounding(schema, said, fields, expected):
    assert keep(schema, said, **fields) == expected


def test_multi_choice_keeps_only_the_items_said(schema):
    assert keep(schema, "maths please", subjects=["Maths", "Science"]) == {"subjects": ["Maths"]}


def test_values_from_earlier_messages_count(schema):
    said = ["Hi I need a math tutor", "Ramya, ICSE"]
    assert keep(schema, said, subjects=["Maths"], board="ICSE") == {
        "subjects": ["Maths"],
        "board": "ICSE",
    }


def test_dropped_names_are_reported(schema):
    _, dropped = grounded(schema, {"schedule": "Monday", "board": "ICSE"}, ["ICSE"])
    assert dropped == ["schedule"]
