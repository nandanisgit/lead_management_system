import pytest

from lead_capture.conversation.guards import problems
from lead_capture.settings import load_settings

LIMITS = load_settings().conversation


def check(reply, lang="en", tutee=()):
    return problems(reply, tutee_texts=list(tutee), language=lang, limits=LIMITS)


def test_good_reply_passes():
    assert check("Great, Class 8 CBSE noted. Online or home tuition?") == []


def test_question_and_word_limits():
    assert "too_many_questions" in check("Name? Class? Board?")
    assert "too_long" in check("word " * 61)


@pytest.mark.parametrize(
    "reply",
    [
        "Tutors usually charge ₹500 per hour.",
        "Most parents pay Rs 6000 a month.",
        "Around 700 rupees is typical.",
        "Budget of 800/- works?",
    ],
)
def test_suggested_amounts_blocked(reply):
    assert "suggested_amount" in check(reply)


def test_amount_the_tutee_stated_is_allowed():
    assert check("Noted, ₹600 per hour.", tutee=["around 600 per hour"]) == []


def test_language_mismatch():
    assert "wrong_language" in check("Which class is he in?", lang="hi")
    assert check("Theek hai, aap kaunsi class mein hain?", lang="hi") == []
    assert "wrong_language" in check("आप किस क्लास में हैं?", lang="en")
