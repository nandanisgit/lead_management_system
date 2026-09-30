"""FR-033: the profile name the greeting used is taken as the contact name, not asked again."""

from tests.integration.harness import Harness, ext


async def test_profile_name_is_used_and_not_asked(session_factory):
    h = Harness(session_factory)
    [consent] = await h.say("Hi, need a maths tutor", profile_name="Nandani")
    assert "Nandani" in consent.text  # the greeting
    h.script(ext(subjects=["Maths"]))
    await h.say(choice="consent:yes")
    assert h.reply_instructions[-1].params["fields"] == ["relationship"]  # name not asked


async def test_summary_shows_contact_name_and_phone(session_factory):
    h = Harness(session_factory)
    await h.say("Hi, need a maths tutor", profile_name="Nandani")
    h.script(ext(subjects=["Maths"], relationship="parent"))
    await h.say(choice="consent:yes")
    h.script(ext(student_name="Aarav", grade_level="Class 8", board="CBSE"))
    await h.say("Aarav, class 8 CBSE")
    await h.say(choice="mode:online")
    h.script(ext(schedule="weekday evenings", start_date="ASAP"))
    await h.say("weekday evenings, asap")
    h.script(ext(budget_min=500, budget_unit="per_hour"))
    [summary] = await h.say("500 per hour")
    assert "Contact: Nandani, +919999900001" in summary.text


async def test_name_the_tutee_gives_wins(session_factory):
    h = Harness(session_factory)
    await h.say("Hi, need a maths tutor", profile_name="Nandu 🌸")
    h.script(ext(subjects=["Maths"], contact_name="Nandani Kumari", relationship="parent"))
    await h.say(choice="consent:yes")
    h.script(ext(student_name="Aarav", grade_level="Class 8", board="CBSE"))
    await h.say("Aarav, class 8 CBSE")
    await h.say(choice="mode:online")
    h.script(ext(schedule="weekday evenings", start_date="ASAP"))
    await h.say("weekday evenings, asap")
    h.script(ext(budget_min=500, budget_unit="per_hour"))
    [summary] = await h.say("500 per hour")
    assert "Contact: Nandani Kumari" in summary.text


async def test_without_profile_name_the_name_is_asked(session_factory):
    h = Harness(session_factory)
    await h.say("Hi, need a maths tutor")
    h.script(ext(subjects=["Maths"]))
    await h.say(choice="consent:yes")
    assert h.reply_instructions[-1].params["fields"] == ["contact_name", "relationship"]
