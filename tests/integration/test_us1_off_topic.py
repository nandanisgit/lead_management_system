from tests.integration.harness import Harness, ext


async def _consented(h):
    await h.say("need a tutor for my son")
    h.script(ext(relationship="parent"))
    await h.say(choice="consent:yes")


async def test_fees_question_gets_fixed_text_and_next_question_without_model_reply(session_factory):
    h = Harness(session_factory)
    await _consented(h)
    replies = len(h.reply_instructions)
    h.script(ext(signals={"asks_fees_or_tutors": True}))
    [r] = await h.say("how much do your tutors charge? who is the best tutor?")
    assert len(h.reply_instructions) == replies  # no model reply call
    assert r.text.startswith("Our team will share fees and tutor details")
    assert "name" in r.text and "₹" not in r.text


async def test_general_off_topic_uses_model_to_answer_briefly_and_steer(session_factory):
    h = Harness(session_factory)
    await _consented(h)
    h.script(ext(signals={"off_topic": True}))
    await h.say("is it raining in Delhi today?")
    ins = h.reply_instructions[-1]
    assert ins.kind == "ANSWER_OFF_TOPIC_AND_STEER" and ins.params["fields"] == ["contact_name"]
