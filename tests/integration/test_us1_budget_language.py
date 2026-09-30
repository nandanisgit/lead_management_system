from tests.integration.harness import Harness, ext


async def _to_budget(h, lang="en"):
    await h.say(
        "I'm Priya, my son Aarav is in class 8 CBSE, needs a maths tutor online, evenings, asap"
    )
    h.script(
        ext(
            lang,
            relationship="parent",
            contact_name="Priya",
            student_name="Aarav",
            grade_level="Class 8",
            board="CBSE",
            subjects=["Maths"],
            mode="online",
            schedule="evenings",
            start_date="ASAP",
        )
    )
    await h.say(choice="consent:yes")


async def test_budget_unsure_never_gets_an_amount(session_factory):
    h = Harness(session_factory)
    await _to_budget(h)
    # the model tries to suggest a rate twice: both rejected by the guards
    h.llm._replies = ["Most parents pay ₹500 per hour, okay?", "Maybe Rs 6000 a month?"]
    h.script(ext())
    [r] = await h.say("not sure, what do others pay?")
    assert "₹" not in r.text and "Rs" not in r.text
    assert "budget" in r.text.lower() and "rough" in r.text.lower()


async def test_hinglish_tutee_gets_hindi_replies(session_factory):
    h = Harness(session_factory)
    [consent] = await h.say("beta ke liye maths tutor chahiye")
    assert "Namaste" in consent.text  # language guessed locally before consent
    h.script(ext("hi", relationship="parent"))
    h.llm._replies = ["What is your name?"]  # English reply to a Hindi tutee → rejected
    [r] = await h.say(choice="consent:yes")
    assert r.text.startswith("Aapka naam")
