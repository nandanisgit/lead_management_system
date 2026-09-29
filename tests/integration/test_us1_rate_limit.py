from tests.integration.harness import Harness


async def test_turn_limit_sends_one_notice_then_stays_silent(session_factory):
    h = Harness(session_factory, conversation={"max_turns_per_contact_per_hour": 3})
    for i in range(3):
        await h.say(f"message {i}")
    sent_before = len(h.channel.sent)
    calls_before = len(h.llm.calls)
    [notice] = await h.say("message 3")  # 4th in the hour
    assert "follow up" in notice.text
    assert await h.say("message 4") == []  # silent
    assert await h.say("message 5") == []
    assert len(h.channel.sent) == sent_before + 1
    assert len(h.llm.calls) == calls_before  # no model calls while limited

    other = await h.say("hello", number="+919999900002")
    assert other and "go ahead" in other[0].text  # other numbers unaffected

    h.clock.advance(hours=1, minutes=1)
    assert await h.say("back again")  # limit period passed
