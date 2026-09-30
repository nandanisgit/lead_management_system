"""T146: one-word answers the model misses are read as answers to the last question."""

from tests.integration.harness import Harness, ext


async def consented(h: Harness) -> None:
    await h.say("Hi, need a maths tutor")
    h.script(ext(subjects=["Maths"]))
    await h.say(choice="consent:yes")


async def test_bare_name_fills_the_name_asked_for(session_factory):
    h = Harness(session_factory)
    await consented(h)
    assert h.reply_instructions[-1].params["fields"] == ["contact_name", "relationship"]
    h.script(ext())  # the model finds nothing in "Nandani"
    await h.say("Nandani")
    assert h.reply_instructions[-1].params["fields"] == ["relationship"]


async def test_bare_choice_fills_the_matching_field(session_factory):
    h = Harness(session_factory)
    await consented(h)
    h.script(ext(contact_name="Priya", relationship="parent", student_name="Aarav"))
    await h.say("I'm Priya, parent of Aarav")
    assert h.reply_instructions[-1].params["fields"] == ["grade_level", "board"]
    h.script(ext())
    await h.say("ICSE")  # not a class, but a valid board
    assert h.reply_instructions[-1].params["fields"] == ["grade_level"]


async def test_the_model_sees_what_was_asked(session_factory):
    h = Harness(session_factory)
    await consented(h)
    h.script(ext(contact_name="Priya"))
    await h.say("Priya")
    [(_, turn)] = [c for c in h.llm.calls if c[0] == "extract"][-1:]
    assert turn.asked == ["contact_name", "relationship"]


async def test_questions_long_replies_and_requests_are_not_guessed(session_factory):
    h = Harness(session_factory)
    await consented(h)
    for text in ["what is this?", "I am not sure what to say here", "/help"]:
        h.script(ext())
        await h.say(text)
        assert h.reply_instructions[-1].params["fields"] == ["contact_name", "relationship"]
    h.script(ext(signals={"wants_human": True}))
    await h.say("human please")
    assert all(ins.params.get("fields") != ["relationship"] for ins in h.reply_instructions)


async def test_free_text_not_guessed_when_two_text_fields_asked(session_factory):
    h = Harness(session_factory, conversation={"short_answer_max_words": 0})
    await consented(h)
    h.script(ext())
    await h.say("Nandani")  # feature off: nothing captured
    assert h.reply_instructions[-1].params["fields"] == ["contact_name", "relationship"]
