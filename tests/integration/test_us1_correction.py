from tests.integration.harness import Harness, ext, to_summary


async def test_correction_at_summary_then_confirm(session_factory):
    h = Harness(session_factory)
    await to_summary(h)
    h.script(ext(schedule="weekends"))
    [revised] = await h.say("change timing to weekends")
    assert "weekends" in revised.text and revised.choices[0].id == "confirm:yes"
    await h.say(choice="confirm:yes")
    [row] = h.leads_rows()
    assert h.cell(row, "Preferred Schedule") == "weekends"


async def test_change_button_asks_what_to_change(session_factory):
    h = Harness(session_factory)
    await to_summary(h)
    [r] = await h.say(choice="confirm:change")
    assert "change" in r.text.lower()
    assert h.leads_rows() == []


async def test_typed_confirmation(session_factory):
    h = Harness(session_factory)
    await to_summary(h)
    h.script(ext(signals={"confirms_summary": True}))
    await h.say("yes all correct")
    assert len(h.leads_rows()) == 1
