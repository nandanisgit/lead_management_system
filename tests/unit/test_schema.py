"""The requirement schema: consistency checks, and adding a field purely through config."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from lead_capture.conversation import fixed_texts as ft
from lead_capture.conversation.summary import lead_values, summary_text
from lead_capture.domain.requirement import Requirement
from lead_capture.domain.schema import RequirementSchema, load_schema
from lead_capture.settings import ROOT

CONFIG = ROOT / "config" / "requirement.yaml"


def raw() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def build(data: dict) -> RequirementSchema:
    return RequirementSchema.model_validate(data)


def test_real_config_loads(schema):
    assert "grade_level" in schema.field_names()
    assert schema.leads_layout().bot_range == "Leads!A:Z"
    assert schema.handoffs_layout().bot_range == "Handoffs!A:H"


def test_adding_a_field_is_config_only(tmp_path: Path):
    """A new field defined only in YAML is extracted, validated, asked, summarised and
    written to the sheet — no code change."""
    data = raw()
    data["lists"]["tutor_genders"] = ["any", "female", "male"]
    data["fields"]["tutor_gender"] = {
        "type": "choice",
        "options": ["tutor_genders"],
        "required": True,
        "buttons": ["tutor_genders"],
        "label": {"en": "tutor preference"},
        "ask": {"en": "Any preference for the tutor's gender?"},
        "llm": {"description": "Preferred tutor gender", "enum": True},
    }
    data["ask_groups"].append({"fields": ["tutor_gender"]})
    data["summary"]["lines"]["en"].append("• Tutor: {tutor_gender}")
    cols = data["sheet"]["leads"]["columns"]
    at = next(i for i, c in enumerate(cols) if c.get("owner") == "ops")
    cols.insert(at, {"header": "Tutor Gender", "value": "field.tutor_gender"})
    path = tmp_path / "requirement.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    schema = load_schema(path)

    props = schema.llm_fields_schema()["properties"]
    assert props["tutor_gender"]["enum"] == ["any", "female", "male"]
    req, rej = Requirement().apply({"tutor_gender": "Female"}, schema, date(2026, 9, 29))
    assert rej == {} and req.get("tutor_gender") == "female"
    assert "tutor_gender" in Requirement().missing_required(schema)
    assert ft.ask_text(["tutor_gender"], "en", schema, {}).startswith("Any preference")
    assert [c.id for c in ft.field_choices("tutor_gender", "en", schema)][0] == "tutor_gender:any"
    assert "• Tutor: female" in summary_text(schema, req, "en", minor_alone=False)
    layout = schema.leads_layout()
    row = lead_values(schema, req, {}, minor_alone=False)
    assert row[layout.index("Tutor Gender")] == "female"
    assert layout.bot_range == "Leads!A:AA"


def test_removing_a_field_is_config_only():
    data = raw()
    del data["fields"]["goal"]
    data["sheet"]["leads"]["columns"] = [
        c for c in data["sheet"]["leads"]["columns"] if c.get("value") != "field.goal"
    ]
    schema = build(data)
    assert "goal" not in schema.llm_fields_schema()["properties"]
    assert "Goal" not in schema.leads_layout().headers


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda d: d["ask_groups"].append({"fields": ["nope"]}), "unknown field 'nope'"),
        (lambda d: d["fields"]["mode"].update(options=["missing_list"]), "unknown list"),
        (lambda d: d["summary"]["lines"]["en"].append("{nope}"), "unknown placeholder"),
        (
            lambda d: d["sheet"]["leads"]["columns"].append({"header": "X", "value": "field.x"}),
            "after ops columns",
        ),
        (lambda d: d["fields"]["schedule"].pop("min_length"), "needs 'min_length'"),
        (lambda d: d["ask_groups"].pop(), "is in no ask_group"),
        (lambda d: d["fields"]["area"].update(typo=1), "Extra inputs"),
    ],
)
def test_inconsistent_config_is_rejected(mutate, message):
    data = raw()
    mutate(data)
    with pytest.raises(ValueError, match=message):
        build(data)


def test_display_rules(schema):
    assert schema.display("board", "N/A", "en") == ""
    assert schema.display("mode", "home", "hi") == "Ghar par tuition"
    assert schema.display("budget_unit", "per_hour", "sheet") == "per hour"
    assert schema.display("budget_min", 600, "sheet") == 600
    assert schema.display("subjects", ["Maths", "EVS"], "en") == "Maths, EVS"


def test_lists_tab(schema):
    tab = schema.lists_tab()
    assert tab["Budget Unit"] == ["per hour", "per month"]
    assert "N/A" in tab["Board"] and tab["Status"][0] == "NEW"
