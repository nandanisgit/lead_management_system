import re

import pytest

from lead_capture.conversation import fixed_texts as ft
from lead_capture.domain.hours import ContactWhen

ALL_KEYS = list(ft._TEXTS)


@pytest.mark.parametrize("key", ALL_KEYS)
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_every_fixed_text_respects_limits(key, lang):
    t = ft.text(
        key, lang, name="Priya", student="Aarav", transcript_days=90, start="10 AM", fields="class"
    )
    assert t.count("?") <= 2
    assert len(t.split()) <= 60
    assert not re.search(r"₹|\brs\.?\s*\d|\d+\s*/-", t, re.I)  # never quotes amounts


def test_language_guess():
    assert ft.guess_language("Hi, need a maths tutor for my son") == "en"
    assert ft.guess_language("beta ke liye maths tutor chahiye") == "hi"
    assert ft.guess_language("मुझे ट्यूटर चाहिए") == "hi"


def test_consent_mentions_retention_and_has_choices():
    t = ft.text("CONSENT", "en", transcript_days=90)
    assert "90 days" in t and "year" in t
    assert [c.id for c in ft.consent_choices("en")] == ["consent:yes", "consent:no"]


def test_ask_text_for_groups_and_singles():
    assert "board" in ft.ask_text(["grade_level", "board"], "en", student="Aarav").lower()
    assert ft.ask_text(["budget_unit"], "hi").startswith("Yeh per hour")


def test_close_completed_by_time_of_day():
    assert "today" in ft.close_completed(ContactWhen.TODAY, "en", "10 AM")
    assert "tomorrow" in ft.close_completed(ContactWhen.AFTER_START_TOMORROW, "en", "10 AM")
    assert "kal" in ft.close_completed(ContactWhen.AFTER_START_TOMORROW, "hi", "10 AM")


def test_every_planner_group_and_field_has_a_fixed_ask():
    from lead_capture.conversation.planner import GROUPS

    for group in GROUPS:
        for fields in [list(group)] + [[f] for f in group]:
            for lang in ("en", "hi"):
                t = ft.ask_text(fields, lang, student="Aarav")
                assert t and t != ft.text("ASK_GENERIC", lang), fields
