from tests.integration.harness import Harness, ext


async def test_one_message_with_many_details_asks_only_whats_missing(session_factory):
    h = Harness(session_factory)
    await h.say("Class 9 CBSE maths and science, home tuition in Dwarka, weekday evenings")
    h.script(
        ext(
            grade_level="Class 9",
            board="CBSE",
            subjects=["Maths", "Science"],
            mode="home",
            area="Dwarka",
            city="Delhi",
            schedule="weekday evenings",
            relationship="parent",
        )
    )
    await h.say(choice="consent:yes")
    asked = [f for ins in h.reply_instructions for f in ins.params.get("fields", [])]
    assert asked == ["contact_name"]

    h.script(ext(contact_name="Priya", student_name="Aarav"))
    await h.say("Priya, my son is Aarav")
    h.script(ext(start_date="ASAP"))
    await h.say("asap")
    asked = [f for ins in h.reply_instructions for f in ins.params.get("fields", [])]
    captured = {
        "grade_level",
        "board",
        "subjects",
        "mode",
        "area",
        "city",
        "schedule",
        "relationship",
        "contact_name",
        "student_name",
    }
    assert not captured & set(asked[1:])  # never re-asked
    assert h.reply_instructions[-1].params["fields"] == ["budget_min", "budget_unit"]
