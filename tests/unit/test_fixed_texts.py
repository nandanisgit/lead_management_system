import re

import pytest

from lead_capture.conversation import fixed_texts as ft
from lead_capture.domain.hours import ContactWhen
from lead_capture.domain.schema import get_schema
from lead_capture.settings import load_settings

LIMITS = load_settings().conversation
CTX = dict(name="Priya", transcript_days=90, start="10 AM", fields="class")


def within_limits(text: str) -> bool:
    return (
        text.count("?") <= LIMITS.max_questions_per_message
        and len(text.split()) <= LIMITS.max_words_per_message
        and not re.search(r"₹|\brs\.?\s*\d|\d+\s*/-", text, re.I)
    )


@pytest.mark.parametrize("key", ft.keys())
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_every_fixed_text_respects_limits(key, lang):
    assert within_limits(ft.text(key, lang, **CTX))


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_every_configured_question_respects_limits(lang):
    schema = get_schema()
    values = {"student_name": "Aarav"}
    for group in schema.ask_groups:
        for fields in [group.fields] + [[f] for f in group.fields]:
            text = ft.ask_text(fields, lang, schema, values)
            assert within_limits(text), text
            assert text != ft.text("ASK_GENERIC", lang), (
                fields
            )  # every askable field has a question


def test_language_guess():
    assert ft.guess_language("Hi, need a maths tutor for my son") == "en"
    assert ft.guess_language("beta ke liye maths tutor chahiye") == "hi"
    assert ft.guess_language("मुझे ट्यूटर चाहिए") == "hi"


def test_consent_mentions_retention_and_has_choices():
    t = ft.text("CONSENT", "en", transcript_days=90)
    assert "90 days" in t and "year" in t and t.startswith("Hi!")
    assert [c.id for c in ft.choices("consent", "en")] == ["consent:yes", "consent:no"]


def test_field_choices_from_config(schema):
    assert [c.title for c in ft.field_choices("mode", "hi", schema)] == [
        "Online",
        "Ghar par",
        "Koi bhi",
    ]
    assert ft.field_choices("schedule", "en", schema) == []
    assert "mode:" in ft.choice_prefixes(schema) and "consent:" in ft.choice_prefixes(schema)


def test_ask_text_uses_student_name(schema):
    assert "Aarav" in ft.ask_text(["grade_level", "board"], "en", schema, {"student_name": "Aarav"})
    assert ft.ask_text(["grade_level"], "hi", schema, {}).startswith("Student kaunsi")


def test_close_completed_by_time_of_day():
    assert "today" in ft.close_completed(ContactWhen.TODAY, "en", "10 AM")
    assert "tomorrow" in ft.close_completed(ContactWhen.AFTER_START_TOMORROW, "en", "10 AM")
    assert "kal" in ft.close_completed(ContactWhen.AFTER_START_TOMORROW, "hi", "10 AM")


def test_detect_language_is_clear_or_none():
    assert ft.detect_language("I need a maths tutor for my son") == "en"
    assert ft.detect_language("Mujhe beti ke liye online maths tutor chahiye") == "hi"
    assert ft.detect_language("मुझे ट्यूटर चाहिए") == "hi"
    assert ft.detect_language("My son is in class 9, CBSE hai") == "en"  # mostly English
    for unclear in ["Nandani", "ICSE", "600", "Class 9", "ok", "", None]:
        assert ft.detect_language(unclear) is None, unclear
