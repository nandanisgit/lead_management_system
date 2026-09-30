"""FR-032: every lead has a phone number — taken from WhatsApp, asked for on Telegram."""

from lead_capture.adapters.channels.fake import FakeChannel
from lead_capture.conversation import fixed_texts as ft
from lead_capture.ports.channel import Capabilities, InboundMessage
from tests.integration.harness import Harness, ext

TG = "tg:5550001"  # a Telegram-style address: not a phone number


def telegram_like() -> FakeChannel:
    """A fake channel that behaves like Telegram: no number, but a share-phone button."""
    return FakeChannel(
        capabilities=Capabilities(
            max_buttons=10,
            max_list_rows=10,
            has_service_window=False,
            window_hours=0,
            contact_is_phone=False,
            can_request_phone=True,
        )
    )


def shared(h: Harness, phone: str) -> InboundMessage:
    return InboundMessage(
        id=f"tg-share-{phone}",
        contact=TG,
        type="contact",
        shared_phone=phone,
        timestamp=h.clock.now(),
    )


async def start(h: Harness) -> list:
    await h.say("Hi, need a maths tutor", number=TG)
    h.script(ext(subjects=["Maths"]))
    await h.say(choice="consent:yes", number=TG)
    h.script(ext(contact_name="Priya", relationship="parent"))
    return await h.say("I'm Priya, his mother", number=TG)


async def test_telegram_asks_for_phone_with_share_button(session_factory):
    h = Harness(session_factory, channel=telegram_like())
    [ask] = await start(h)
    assert h.reply_instructions[-1].params["fields"] == ["phone"]
    assert ask.phone_request_label == ft.text("SHARE_PHONE_BUTTON", "en")


async def test_shared_phone_is_used_without_a_model_call(session_factory):
    h = Harness(session_factory, channel=telegram_like())
    await start(h)
    calls = h.extract_calls
    before = len(h.channel.sent)
    await h.deliver(shared(h, "919876543210"))
    [nxt] = [m for to, m in h.channel.sent[before:] if to == TG]
    assert h.extract_calls == calls  # structured input: no extraction
    assert nxt.phone_request_label is None
    assert nxt.text == ft.ask_text(["student_name"], "en", h.sv.schema, {})  # moved on


async def test_typed_phone_is_normalised_and_recorded(session_factory):
    h = Harness(session_factory, channel=telegram_like())
    await start(h)
    h.script(ext(phone="098765 43210", student_name="Aarav", grade_level="Class 8", board="CBSE"))
    await h.say("098765 43210. My son Aarav, class 8 CBSE", number=TG)
    await h.say(choice="mode:online", number=TG)
    h.script(ext(schedule="weekday evenings", start_date="ASAP"))
    await h.say("weekday evenings, asap", number=TG)
    h.script(ext(budget_min=500, budget_unit="per_hour"))
    [summary] = await h.say("500 per hour", number=TG)
    assert [c.id for c in summary.choices] == ["confirm:yes", "confirm:change"]
    await h.say(choice="confirm:yes", number=TG)
    [row] = h.leads_rows()
    assert h.cell(row, "Phone Number") == "'+919876543210"


async def test_whatsapp_number_fills_phone_and_is_never_asked(session_factory):
    h = Harness(session_factory)  # default fake channel: address is the phone number
    await h.say("Hi, need a maths tutor")
    h.script(ext(subjects=["Maths"]))
    [r] = await h.say(choice="consent:yes")
    h.script(ext(contact_name="Priya", relationship="parent"))
    [r] = await h.say("I'm Priya, his mother")
    assert h.reply_instructions[-1].params["fields"] == ["student_name"]
    assert r.phone_request_label is None


async def test_phone_before_consent_is_not_stored(session_factory):
    h = Harness(session_factory, channel=telegram_like())
    await h.say("Hi", number=TG)
    before = len(h.channel.sent)
    await h.deliver(shared(h, "919876543210"))
    [reask] = [m for to, m in h.channel.sent[before:] if to == TG]
    assert [c.id for c in reask.choices] == ["consent:yes", "consent:no"]
    assert h.leads_rows() == [] and h.extract_calls == 0
