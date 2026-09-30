"""Validation and cross-field rules, all driven by config/requirement.yaml."""

from datetime import date

import pytest

from lead_capture.domain.requirement import OUT_OF_AREA, Requirement

TODAY = date(2026, 9, 29)


def apply(schema, req=None, **fields):
    return (req or Requirement()).apply(fields, schema, TODAY)


def full(schema, **over) -> Requirement:
    base = dict(
        contact_name="Priya",
        relationship="parent",
        phone="9876543210",
        student_name="Aarav",
        grade_level="Class 8",
        board="CBSE",
        subjects=["Maths", "Science"],
        mode="home",
        area="Dwarka Sector 12",
        city="Delhi",
        schedule="weekdays after 5 pm",
        start_date="ASAP",
        budget_min=600,
        budget_unit="per_hour",
    )
    base.update(over)
    req, rejected = apply(schema, **base)
    assert rejected == {}, rejected
    return req


def test_complete_requirement_has_nothing_missing(schema):
    req = full(schema)
    assert req.missing_required(schema) == []
    assert req.get("budget_max") == 600  # single figure sets both


def test_missing_follows_ask_group_order(schema):
    assert Requirement().missing_required(schema)[:5] == [
        "contact_name",
        "relationship",
        "phone",
        "student_name",
        "grade_level",
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("contact_name", ""),
        ("contact_name", "x" * 61),
        ("relationship", "uncle"),
        ("grade_level", "Class 13"),
        ("board", "Oxford"),
        ("subjects", []),
        ("subjects", ["Maths", "Science", "English", "Hindi", "EVS", "Coding"]),
        ("subjects", ["Astrology"]),
        ("mode", "hybrid"),
        ("area", "x"),
        ("schedule", "ok"),
        ("start_date", "2027-12-01"),
        ("start_date", "2026-09-01"),
        ("budget_min", 0),
        ("budget_unit", "per_week"),
        ("goal", "x" * 121),
        ("sessions_per_week", 8),
        ("tutor_preferences", "x" * 201),
        ("level_notes", "x" * 301),
        ("email", "nope"),
        ("pincode", "12345"),
        ("guardian_name", ""),
        ("guardian_relationship", "neighbour"),
    ],
)
def test_invalid_values_rejected_with_reason(schema, field, value):
    req, rejected = apply(schema, **{field: value})
    assert rejected.get(field) and req.get(field) is None


def test_normalisation(schema):
    req, rej = apply(
        schema,
        grade_level="9th",
        board="cbse",
        subjects=["math", "sst"],
        city="Gurgaon",
        budget_unit="per month",
    )
    assert rej == {}
    assert req.get("grade_level") == "Class 9" and req.get("board") == "CBSE"
    assert req.get("subjects") == ["Maths", "Social Science"]
    assert req.get("city") == "Gurugram" and req.get("budget_unit") == "per_month"


def test_board_required_until_level_known_then_only_for_school(schema):
    assert "board" in Requirement().missing_required(schema)
    req = full(schema, grade_level="Undergraduate", board=None)
    assert "board" not in req.missing_required(schema) and req.get("board") == "N/A"
    req, _ = apply(schema, grade_level="Class 9")
    assert "board" in req.missing_required(schema)


def test_location_required_only_when_not_online(schema):
    req, _ = apply(schema, mode="online")
    assert not {"area", "city"} & set(req.missing_required(schema))
    req, _ = apply(schema, mode="home")
    assert {"area", "city"} <= set(req.missing_required(schema))


def test_non_ncr_city_for_home_is_out_of_area(schema):
    req, rej = apply(schema, mode="home", city="Pune")
    assert rej["city"] == OUT_OF_AREA and req.out_of_area


def test_either_outside_ncr_becomes_online(schema):
    req, rej = apply(schema, mode="either", city="Pune", area="Kothrud")
    assert req.get("mode") == "online" and req.get("city") is None and req.get("area") is None
    assert "city" not in rej and not req.out_of_area


def test_pincode_outside_ncr_for_home_is_out_of_area(schema):
    req, rej = apply(schema, mode="home", pincode="411001")
    assert rej["pincode"] == OUT_OF_AREA and req.out_of_area


def test_budget_rules(schema):
    _, rej = apply(schema, budget_min=800, budget_max=500)
    assert "budget_max" in rej
    req, rej = apply(schema, budget_min=500, budget_max=800)
    assert (req.get("budget_min"), req.get("budget_max")) == (500, 800) and rej == {}


def test_student_name_copied_for_students(schema):
    req, _ = apply(schema, contact_name="Riya", relationship="student")
    assert req.get("student_name") == "Riya"


def test_latest_value_wins(schema):
    req, rej = apply(schema, full(schema), grade_level="Class 10")
    assert req.get("grade_level") == "Class 10" and rej == {}


def test_guardian_required_only_for_minor_alone(schema):
    req = full(schema, relationship="student", contact_name="Aarav")
    assert req.is_minor_alone(schema)
    assert req.missing_required(schema, minor_alone=True) == [
        "guardian_name",
        "guardian_relationship",
    ]
    assert not full(schema).is_minor_alone(schema)


def test_unknown_fields_ignored(schema):
    req, rej = apply(schema, favourite_colour="blue")
    assert rej == {} and req.captured() == {}


def test_round_trip_and_old_format(schema):
    req = full(schema)
    assert Requirement.from_dict(req.to_dict()).values == req.values
    old = Requirement.from_dict({"grade_level": "Class 8", "subjects": [], "out_of_area": False})
    assert old.values == {"grade_level": "Class 8"}
