from datetime import datetime

import pytest

from tests.integration.harness import Harness, ext, to_summary


async def test_full_conversation_records_one_new_lead(session_factory):
    h = Harness(session_factory)

    [consent] = await h.say("Hi, need a maths tutor for my son")
    assert "go ahead" in consent.text and [c.id for c in consent.choices] == [
        "consent:yes",
        "consent:no",
    ]
    assert h.extract_calls == 0  # nothing extracted or stored before consent (FR-005)

    h.script(ext(subjects=["Maths"], relationship="parent"))
    [r] = await h.say(choice="consent:yes")
    assert h.extract_calls == 1  # the opening message is read only after consent
    assert h.reply_instructions[-1].params["fields"] == ["contact_name"]

    h.script(ext(contact_name="Priya", student_name="Aarav", grade_level="Class 8", board="CBSE"))
    [r] = await h.say("I'm Priya, he's Aarav in class 8 CBSE")
    assert h.reply_instructions[-1].params["fields"] == ["mode"]
    assert [c.id for c in r.choices] == ["mode:online", "mode:home", "mode:either"]

    calls = h.extract_calls
    [r] = await h.say(choice="mode:home")  # button tap: no model call at all
    assert h.extract_calls == calls and "area" in r.text.lower()

    h.script(
        ext(
            area="Dwarka Sector 12", city="Delhi", schedule="weekdays after 5 pm", start_date="ASAP"
        )
    )
    await h.say("Dwarka Sector 12, Delhi. Weekdays after 5, start asap")
    assert h.reply_instructions[-1].params["fields"] == ["budget_min", "budget_unit"]

    h.script(ext(budget_min=600, budget_unit="per_hour"))
    [summary] = await h.say("600 per hour")
    assert "Aarav, Class 8 CBSE" in summary.text and "₹600 per hour" in summary.text
    assert [c.id for c in summary.choices] == ["confirm:yes", "confirm:change"]
    assert h.leads_rows() == []  # nothing recorded before confirmation

    [close] = await h.say(choice="confirm:yes")
    assert "today" in close.text
    [row] = h.leads_rows()
    expected = {
        "Status": "NEW",
        "Contact Name": "Priya",
        "Relationship": "parent",
        "Student Name": "Aarav",
        "Class / Level": "Class 8",
        "Board": "CBSE",
        "Subjects": "Maths",
        "Mode": "home",
        "Area": "Dwarka Sector 12",
        "City": "Delhi",
        "Budget Min (₹)": 600,
        "Budget Max (₹)": 600,
        "Budget Unit": "per hour",
        "WhatsApp Number": "'+919999900001",
        "Language": "English",
    }
    assert {k: h.cell(row, k) for k in expected} == expected
    assert h.cell(row, "Lead ID").startswith("L-20260929-")


@pytest.mark.parametrize(
    "hour,expected", [(15, "today"), (19, "after 10 AM tomorrow"), (8, "after 10 AM today")]
)
async def test_closing_message_depends_on_time_of_day(session_factory, hour, expected):
    h = Harness(session_factory, at=datetime(2026, 9, 29, hour, 0))
    await to_summary(h)
    [close] = await h.say(choice="confirm:yes")
    assert expected in close.text


async def test_every_bot_message_respects_question_limit(session_factory):
    h = Harness(session_factory)
    await to_summary(h)
    await h.say(choice="confirm:yes")
    for _, msg in h.channel.sent:
        assert msg.text.count("?") <= 2


async def test_model_skipped_for_taps_only_when_setting_on(session_factory):
    h = Harness(session_factory, llm={"skip_for_deterministic_turns": False})
    await h.say("Hi")
    h.script(ext(signals={"consent": "given"}))
    await h.say(choice="consent:yes")
    calls = h.extract_calls
    h.script(ext(mode="home"))
    await h.say(choice="mode:home")
    assert h.extract_calls == calls + 1
