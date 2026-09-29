from datetime import date

import pytest

from lead_capture.domain.lists import load_lists
from lead_capture.domain.requirement import OUT_OF_AREA, RequirementState

LISTS = load_lists()
TODAY = date(2026, 9, 29)


def apply(state, **fields):
    return state.apply(fields, LISTS, TODAY)


def full_state(**over) -> RequirementState:
    s = RequirementState()
    base = dict(
        contact_name="Priya",
        relationship="parent",
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
    s, rejected = apply(s, **base)
    assert rejected == {}, rejected
    return s


def test_complete_state_has_nothing_missing():
    s = full_state()
    assert s.missing_required() == []
    assert s.budget_max == 600  # single figure sets both


def test_missing_order_follows_data_model():
    s = RequirementState()
    assert s.missing_required()[:4] == [
        "contact_name",
        "relationship",
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
        ("email", "not-an-email"),
        ("pincode", "12345"),
        ("guardian_name", ""),
        ("guardian_relationship", "neighbour"),
    ],
)
def test_invalid_values_rejected_with_reason(field, value):
    s, rejected = apply(RequirementState(), **{field: value})
    assert field in rejected and rejected[field]
    assert getattr(s, field) in (None, [])


def test_normalisation():
    s, rej = apply(
        RequirementState(),
        grade_level="9th",
        board="cbse",
        subjects=["math", "sst"],
        city="Gurgaon",
        budget_unit="per month",
    )
    assert rej == {}
    assert s.grade_level == "Class 9" and s.board == "CBSE"
    assert s.subjects == ["Maths", "Social Science"]
    assert s.city == "Gurugram" and s.budget_unit == "per_month"


def test_board_required_only_for_school_grades():
    s = full_state(grade_level="Undergraduate", board=None)
    assert "board" not in s.missing_required()
    assert s.board == "N/A"
    s2, _ = apply(RequirementState(), grade_level="Class 9")
    assert "board" in s2.missing_required()


def test_location_required_only_when_not_online():
    s, _ = apply(RequirementState(), mode="online")
    assert "area" not in s.missing_required() and "city" not in s.missing_required()
    s, _ = apply(RequirementState(), mode="home")
    assert "area" in s.missing_required() and "city" in s.missing_required()


def test_non_ncr_city_for_home_is_out_of_area():
    s, rej = apply(RequirementState(), mode="home", city="Pune")
    assert rej["city"] == OUT_OF_AREA
    assert s.out_of_area is True


def test_either_outside_ncr_becomes_online():
    s, rej = apply(RequirementState(), mode="either", city="Pune", area="Kothrud")
    assert s.mode == "online" and s.city is None and s.area is None
    assert "city" not in rej and s.out_of_area is False


def test_pincode_outside_ncr_for_home_is_out_of_area():
    s, rej = apply(RequirementState(), mode="home", pincode="411001")
    assert rej["pincode"] == OUT_OF_AREA and s.out_of_area


def test_budget_rules():
    s, rej = apply(RequirementState(), budget_min=800, budget_max=500)
    assert "budget_max" in rej
    s, rej = apply(RequirementState(), budget_min=500, budget_max=800)
    assert (s.budget_min, s.budget_max) == (500, 800) and rej == {}


def test_student_name_defaults_to_contact_for_students():
    s, _ = apply(RequirementState(), contact_name="Riya", relationship="student")
    assert s.student_name == "Riya"


def test_latest_value_wins():
    s = full_state()
    s, rej = apply(s, grade_level="Class 10")
    assert s.grade_level == "Class 10" and rej == {}


def test_guardian_required_only_for_minor_alone():
    s = full_state(relationship="student", contact_name="Aarav")
    assert s.is_minor_alone(LISTS) is True
    assert s.missing_required(minor_alone=True)[-2:] == ["guardian_name", "guardian_relationship"]
    s = full_state(relationship="parent")
    assert s.is_minor_alone(LISTS) is False
    assert "guardian_name" not in s.missing_required(minor_alone=False)


def test_unknown_fields_ignored():
    s, rej = apply(RequirementState(), favourite_colour="blue")
    assert rej == {} and not hasattr(s, "favourite_colour")
