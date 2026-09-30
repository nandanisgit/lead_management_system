"""T150: a model error or timeout is not the tutee's fault."""

from lead_capture.conversation import fixed_texts as ft
from lead_capture.store.models import Conversation
from tests.integration.harness import Harness, ext


async def test_timeout_reasks_the_question_without_a_strike(session_factory):
    h = Harness(session_factory)
    await h.say("Hi, I need a maths tutor")
    h.script(ext(subjects=["Maths"]))
    await h.say(choice="consent:yes")
    h.llm._timeout = True  # the local model is too slow / down
    [reply] = await h.say("my son needs help")
    assert reply.text != ft.text("REPHRASE", "en")
    assert reply.text == ft.ask_text(["contact_name", "relationship"], "en", h.sv.schema, {})
    with session_factory() as db:
        assert db.query(Conversation).one().misunderstand_streak == 0


async def test_short_answer_still_captured_when_the_model_fails(session_factory):
    h = Harness(session_factory)
    await h.say("Hi, I need a maths tutor")
    h.script(ext(subjects=["Maths"], contact_name="Priya", relationship="parent"))
    await h.say(choice="consent:yes")
    h.llm._timeout = True
    [reply] = await h.say("Aarav")  # the student's name, asked next
    expected = ft.ask_text(["grade_level", "board"], "en", h.sv.schema, {"student_name": "Aarav"})
    assert reply.text == expected  # name captured, next question asked
