"""T148: the bot replies in the tutee's language and never switches on its own."""

from tests.integration.harness import Harness, ext


async def english_start(h: Harness) -> None:
    await h.say("Hi, I need a maths tutor for my son")
    h.script(ext(subjects=["Maths"]))
    await h.say(choice="consent:yes")


async def test_short_answers_keep_english_even_if_model_says_hindi(session_factory):
    h = Harness(session_factory)
    await english_start(h)
    h.script(ext("hi", contact_name="Nandani"))  # model wrongly reports Hindi
    [reply] = await h.say("Nandani")
    h.script(ext("hi", board="ICSE"))
    [reply2] = await h.say("ICSE")
    assert "Kya" not in reply.text + reply2.text and "hai" not in reply.text + reply2.text
    [(_, turn)] = [c for c in h.llm.calls if c[0] == "extract"][-1:]
    assert turn.language == "en"


async def test_switches_when_the_tutee_writes_hinglish_and_stays(session_factory):
    h = Harness(session_factory)
    await english_start(h)
    h.script(ext(contact_name="Priya"))
    await h.say("Mujhe beti ke liye tutor chahiye, mera naam Priya hai")
    h.script(ext("en", relationship="parent"))  # model says English; the tutee didn't
    await h.say("parent")  # unclear: stays Hindi
    [(_, turn)] = [c for c in h.llm.calls if c[0] == "extract"][-1:]
    assert turn.language == "hi"


async def test_switches_back_to_english_when_the_tutee_does(session_factory):
    h = Harness(session_factory)
    await h.say("Namaste, beti ke liye tutor chahiye")
    h.script(ext(subjects=["Maths"]))
    await h.say(choice="consent:yes")
    h.script(ext(contact_name="Priya"))
    await h.say("I am Priya, her mother, and we are looking for help with maths")
    [(_, turn)] = [c for c in h.llm.calls if c[0] == "extract"][-1:]
    assert turn.language == "en"
