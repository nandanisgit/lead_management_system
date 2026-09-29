from tests.integration.harness import Harness, ext


async def _student_to_guardian(h, **signals):
    await h.say("hi i need maths tuition")
    h.script(
        ext(
            relationship="student",
            contact_name="Aarav",
            grade_level="Class 9",
            board="CBSE",
            subjects=["Maths"],
            mode="online",
            schedule="evenings",
            start_date="ASAP",
            budget_min=500,
            budget_unit="per_hour",
        )
    )
    await h.say(choice="consent:yes")


async def test_student_alone_is_asked_for_guardian_and_flagged(session_factory):
    h = Harness(session_factory)
    await _student_to_guardian(h)
    ins = h.reply_instructions[-1]
    assert ins.params["fields"] == ["guardian_name", "guardian_relationship"] and ins.strict

    h.script(ext(signals={"off_topic": True}))
    [r] = await h.say("which cricket team do you like?")
    assert r.text.startswith("Let's get your tutor sorted first.")  # one-line redirect only

    h.script(ext(guardian_name="Sunita", guardian_relationship="mother"))
    [summary] = await h.say("my mom Sunita")
    assert "share this with your parent" in summary.text
    await h.say(choice="confirm:yes")
    [row] = h.leads_rows()
    assert row[21].startswith("MINOR – consent given by student – contact parent/guardian: Sunita")


async def test_parent_for_class_9_child_not_asked_for_guardian(session_factory):
    h = Harness(session_factory)
    await h.say("need tutor for my daughter")
    h.script(
        ext(
            relationship="parent",
            contact_name="Priya",
            student_name="Riya",
            grade_level="Class 9",
            board="CBSE",
            subjects=["Maths"],
            mode="online",
            schedule="evenings",
            start_date="ASAP",
            budget_min=500,
            budget_unit="per_hour",
        )
    )
    [summary] = await h.say(choice="consent:yes")
    assert summary.choices[0].id == "confirm:yes"


async def test_model_signal_alone_triggers_rule(session_factory):
    h = Harness(session_factory)
    await h.say("hello")
    h.script(
        ext(
            relationship="other",
            contact_name="Kabir",
            student_name="Kabir",
            grade_level="Undergraduate",
            subjects=["Maths"],
            mode="online",
            schedule="evenings",
            start_date="ASAP",
            budget_min=500,
            budget_unit="per_hour",
            signals={"likely_minor_alone": True},
        )
    )
    await h.say(choice="consent:yes")
    assert h.reply_instructions[-1].params["fields"] == ["guardian_name", "guardian_relationship"]
