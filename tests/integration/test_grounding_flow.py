"""T151 end to end: invented values are never stored; what the tutee said is."""

from lead_capture.store.models import Conversation
from tests.integration.harness import Harness, ext


def collected(session_factory) -> dict:
    with session_factory() as db:
        return db.query(Conversation).order_by(Conversation.id.desc()).first().collected["values"]


async def test_invented_details_are_not_stored_and_are_asked_for(session_factory):
    h = Harness(session_factory)
    await h.say("Hi, I need a maths tutor for my daughter Ramya, I'm Nandani")
    h.script(ext(subjects=["Maths"], relationship="parent", contact_name="Nandani"))
    await h.say(choice="consent:yes")
    # the model "helpfully" invents a class, schedule, start date and mode
    h.script(
        ext(
            student_name="Ramya",
            grade_level="Class 8",
            schedule="Monday and Wednesday",
            start_date="ASAP",
            mode="online",
        )
    )
    await h.say("Ramya")
    values = collected(session_factory)
    assert values["student_name"] == "Ramya"
    assert not {"grade_level", "schedule", "start_date", "mode"} & set(values)
    assert h.reply_instructions[-1].params["fields"][0] == "grade_level"  # asked, not assumed


async def test_typed_yes_gives_consent_without_the_model(session_factory):
    h = Harness(session_factory)
    await h.say("Hi, I need a maths tutor")
    calls = h.extract_calls
    await h.say("yes")
    assert h.extract_calls == calls + 1  # only the opening message is read, not the "yes"
    with session_factory() as db:
        assert db.query(Conversation).one().state == "in_progress"  # consent given


async def test_short_answer_goes_to_the_asked_field_not_notes(session_factory):
    h = Harness(session_factory)
    await h.say("I'm Priya, maths tutor needed for my son Aarav, class 8 CBSE, home tuition")
    h.script(
        ext(
            contact_name="Priya",
            relationship="parent",
            subjects=["Maths"],
            student_name="Aarav",
            grade_level="Class 8",
            board="CBSE",
            mode="home",
        )
    )
    await h.say(choice="consent:yes")
    assert h.reply_instructions[-1].params["fields"] == ["area", "city"]
    h.script(ext(level_notes="NOIDA"))  # the model files the city under notes
    await h.say("NOIDA")
    values = collected(session_factory)
    assert values.get("city") == "Noida" and "level_notes" not in values
    assert h.reply_instructions[-1].params["fields"] == ["area"]
