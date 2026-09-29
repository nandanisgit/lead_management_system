"""Fixed English / Hindi (Hinglish, Roman script) texts for turns code can answer on its own.

Used for deterministic turns (llm.skip_for_deterministic_turns) and as the fallback whenever a
model reply fails the guards. Every text keeps to ≤ 2 questions and ≤ 60 words.
"""

from __future__ import annotations

import re
from typing import Any

from lead_capture.domain.hours import ContactWhen
from lead_capture.ports.channel import Choice

Lang = str  # "en" | "hi"

_HINGLISH = re.compile(
    r"\b(chahiye|chahie|hai|hain|ke liye|mujhe|mera|meri|beta|beti|bacch[ae]|kya|aap|ji|"
    r"karna|padhai|padhana|nahi|haan|kitna|kaise|abhi)\b",
    re.I,
)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def guess_language(text: str | None) -> Lang:
    if not text:
        return "en"
    if _DEVANAGARI.search(text) or len(_HINGLISH.findall(text)) >= 1:
        return "hi"
    return "en"


def _name(p: dict, key: str = "name") -> str:
    v = p.get(key)
    return f" {v}" if v else ""


_TEXTS: dict[str, dict[Lang, str]] = {
    "CONSENT": {
        "en": "Hi{name}! I'm the tutoring team's assistant and I'll help you find the right tutor. "
        "To do that I'll save the details you share; chats are kept {transcript_days} days and "
        "requests for up to a year. Shall we go ahead?",
        "hi": "Namaste{name}! Main tutoring team ki assistant hoon aur sahi tutor dhoondhne mein "
        "aapki madad karungi. Iske liye aapki di hui details save hongi; chat {transcript_days} "
        "din aur request ek saal tak rakhi jaati hai. Kya hum aage badhein?",
    },
    "CONSENT_REASK": {
        "en": "Sorry, I didn't catch that. Is it okay for me to save your details so we can find "
        "you a tutor?",
        "hi": "Maaf kijiye, samajh nahi paayi. Kya main aapki details save kar sakti hoon "
        "taaki hum tutor dhoondh sakein?",
    },
    "CLOSE_DECLINED": {
        "en": "No problem, I haven't saved anything. If you change your mind, just message us "
        "here anytime.",
        "hi": "Koi baat nahi, maine kuch save nahi kiya. Mann badle toh kabhi bhi yahan message "
        "kar dijiye.",
    },
    "ASK_OPEN": {
        "en": "Great! Tell me a bit about what you're looking for — which class, subjects, and "
        "whether you'd like online or home tuition.",
        "hi": "Badhiya! Thoda bataiye aapko kya chahiye — kaunsi class, kaunse subjects, aur "
        "online ya home tuition?",
    },
    "ASK_contact_name_relationship": {
        "en": "May I know your name, and are you the parent or the student?",
        "hi": "Aapka naam kya hai, aur aap parent hain ya student?",
    },
    "ASK_contact_name": {
        "en": "May I know your name?",
        "hi": "Aapka naam kya hai?",
    },
    "ASK_relationship": {
        "en": "Are you the parent or the student?",
        "hi": "Aap parent hain ya student?",
    },
    "ASK_GENERIC": {
        "en": "Could you tell me a little more about what you need?",
        "hi": "Kya aap thoda aur bata sakte hain ki aapko kya chahiye?",
    },
    "ASK_student_name": {
        "en": "What's the student's name?",
        "hi": "Student ka naam kya hai?",
    },
    "ASK_grade_level_board": {
        "en": "Which class is{student} in, and which board — CBSE, ICSE or State?",
        "hi": "{student_hi} kaunsi class mein hai, aur board kaunsa hai — CBSE, ICSE ya State?",
    },
    "ASK_grade_level": {
        "en": "Which class or level is{student} in?",
        "hi": "{student_hi} kaunsi class ya level mein hai?",
    },
    "ASK_board": {
        "en": "Which board is it?",
        "hi": "Board kaunsa hai?",
    },
    "ASK_subjects": {
        "en": "Which subjects do you need help with?",
        "hi": "Kaunse subjects ke liye tutor chahiye?",
    },
    "ASK_mode": {
        "en": "Would you prefer online classes or a tutor coming home?",
        "hi": "Aap online classes chahenge ya ghar par tutor?",
    },
    "ASK_area_city": {
        "en": "Which area and city are you in? (Home tuition is available across Delhi/NCR.)",
        "hi": "Aap kis area aur city mein hain? (Home tuition Delhi/NCR mein available hai.)",
    },
    "ASK_area": {
        "en": "Which area are you in?",
        "hi": "Aap kis area mein hain?",
    },
    "ASK_city": {
        "en": "Which city is that in?",
        "hi": "Yeh kis city mein hai?",
    },
    "ASK_schedule": {
        "en": "Which days and times usually work best?",
        "hi": "Kaunse din aur kis time aapke liye theek rahega?",
    },
    "ASK_start_date": {
        "en": "When would you like to start — as soon as possible, or a specific date?",
        "hi": "Kab se shuru karna chahenge — jaldi se jaldi, ya koi khaas date?",
    },
    "ASK_budget_min_budget_unit": {
        "en": "Do you have a budget in mind, per hour or per month? A rough figure is fine.",
        "hi": "Aapka budget kitna hai, per hour ya per month? Andaaz se bata dijiye.",
    },
    "ASK_budget_min": {
        "en": "Roughly what budget would you be comfortable with?",
        "hi": "Andaazan kitna budget theek rahega?",
    },
    "ASK_budget_unit": {
        "en": "Is that per hour or per month?",
        "hi": "Yeh per hour hai ya per month?",
    },
    "ASK_guardian_name_guardian_relationship": {
        "en": "Could you share your parent's or guardian's name, and how they're related to you? "
        "Our team will speak with them.",
        "hi": "Apne parent ya guardian ka naam bata sakte ho, aur woh aapke kya lagte hain? Hamari "
        "team unse baat karegi.",
    },
    "ASK_guardian_name": {
        "en": "What's your parent's or guardian's name?",
        "hi": "Apne parent ya guardian ka naam bataoge?",
    },
    "ASK_guardian_relationship": {
        "en": "How are they related to you — mother, father or guardian?",
        "hi": "Woh aapke kya lagte hain — mummy, papa ya guardian?",
    },
    "CLARIFY": {
        "en": "Sorry, I couldn't use that — could you check the {fields}?",
        "hi": "Maaf kijiye, yeh samajh nahi aaya — kya aap {fields} dobara bata sakte hain?",
    },
    "SUMMARY_LEAD_IN": {
        "en": "Here's what I have:",
        "hi": "Maine yeh note kiya hai:",
    },
    "SUMMARY_CONFIRM": {
        "en": "Is this all correct?",
        "hi": "Kya sab sahi hai?",
    },
    "SUMMARY_MINOR": {
        "en": "Please share this with your parent or guardian too.",
        "hi": "Ise apne parent ya guardian ke saath bhi share kar dena.",
    },
    "ASK_CHANGE": {
        "en": "Sure — what would you like to change?",
        "hi": "Zaroor — kya badalna hai?",
    },
    "CLOSE_COMPLETED_today": {
        "en": "Thank you! I've passed this to our team and they'll get in touch with you today.",
        "hi": "Dhanyavaad! Maine yeh team ko bhej diya hai, woh aaj hi aapse sampark karenge.",
    },
    "CLOSE_COMPLETED_after_start_today": {
        "en": "Thank you! I've passed this to our team and they'll reach out after {start} today.",
        "hi": "Dhanyavaad! Maine yeh team ko bhej diya hai, woh aaj {start} ke baad sampark "
        "karenge.",
    },
    "CLOSE_COMPLETED_after_start_tomorrow": {
        "en": "Thank you! I've passed this to our team and they'll reach out after {start} "
        "tomorrow.",
        "hi": "Dhanyavaad! Maine yeh team ko bhej diya hai, woh kal {start} ke baad sampark "
        "karenge.",
    },
    "POST_COMPLETION": {
        "en": "Thanks! Our team has your request and will be in touch. If you need a tutor for "
        "someone else too, just tell me.",
        "hi": "Dhanyavaad! Team ke paas aapki request hai, woh sampark karenge. Kisi aur ke liye "
        "bhi tutor chahiye toh bata dijiye.",
    },
    "REPHRASE": {
        "en": "Sorry, I didn't quite get that. Could you say it another way?",
        "hi": "Maaf kijiye, theek se samajh nahi aaya. Kya aap doosre tareeke se bata sakte hain?",
    },
    "FEES_OR_TUTORS": {
        "en": "Our team will share fees and tutor details once they've reviewed your request.",
        "hi": "Fees aur tutor ki details team aapki request dekhkar share karegi.",
    },
    "OFF_TOPIC_REDIRECT": {
        "en": "Let's get your tutor sorted first.",
        "hi": "Pehle aapke liye tutor dhoondh lete hain.",
    },
    "RATE_LIMITED": {
        "en": "Thanks for your messages! Our team will follow up with you shortly.",
        "hi": "Aapke messages ke liye dhanyavaad! Hamari team jaldi aapse sampark karegi.",
    },
    "ASK_FOR_TEXT": {
        "en": "Sorry, I can only read text messages. Could you type your answer?",
        "hi": "Maaf kijiye, main sirf text message padh sakti hoon. Kya aap type karke bata sakte "
        "hain?",
    },
}

FIELD_LABELS: dict[str, dict[Lang, str]] = {
    "contact_name": {"en": "your name", "hi": "aapka naam"},
    "relationship": {"en": "parent or student", "hi": "parent ya student"},
    "student_name": {"en": "student's name", "hi": "student ka naam"},
    "grade_level": {"en": "class", "hi": "class"},
    "board": {"en": "board", "hi": "board"},
    "subjects": {"en": "subjects", "hi": "subjects"},
    "mode": {"en": "online or home", "hi": "online ya home"},
    "area": {"en": "area", "hi": "area"},
    "city": {"en": "city", "hi": "city"},
    "pincode": {"en": "PIN code", "hi": "PIN code"},
    "schedule": {"en": "days and times", "hi": "din aur time"},
    "start_date": {"en": "start date", "hi": "shuru karne ki date"},
    "budget_min": {"en": "budget", "hi": "budget"},
    "budget_max": {"en": "budget", "hi": "budget"},
    "budget_unit": {"en": "per hour or per month", "hi": "per hour ya per month"},
    "guardian_name": {"en": "parent's or guardian's name", "hi": "parent/guardian ka naam"},
    "guardian_relationship": {"en": "how they're related", "hi": "rishta"},
    "email": {"en": "email", "hi": "email"},
}


def text(key: str, lang: Lang = "en", **params: Any) -> str:
    variants = _TEXTS[key]
    template = variants.get(lang) or variants["en"]
    student = params.get("student")
    params = {
        "name": _name(params),
        "student": f" {student}" if student else "",
        "student_hi": student or "Student",
        **{k: v for k, v in params.items() if k not in ("name", "student")},
    }
    return template.format(**params)


def ask_key(fields: list[str]) -> str:
    return "ASK_" + "_".join(fields)


def ask_text(fields: list[str], lang: Lang, **params: Any) -> str:
    key = ask_key(fields)
    if key in _TEXTS:
        return text(key, lang, **params)
    parts = [text(ask_key([f]), lang, **params) for f in fields if ask_key([f]) in _TEXTS]
    return " ".join(parts) or text("ASK_GENERIC", lang)


def clarify_text(fields: list[str], lang: Lang) -> str:
    labels = ", ".join(FIELD_LABELS.get(f, {}).get(lang, f) for f in fields)
    return text("CLARIFY", lang, fields=labels)


def consent_choices(lang: Lang) -> list[Choice]:
    yes, no = ("Haan, aage badhein", "Nahi") if lang == "hi" else ("Yes, go ahead", "No")
    return [Choice(id="consent:yes", title=yes), Choice(id="consent:no", title=no)]


def mode_choices(lang: Lang) -> list[Choice]:
    home = "Ghar par" if lang == "hi" else "Home"
    either = "Koi bhi" if lang == "hi" else "Either"
    return [
        Choice(id="mode:online", title="Online"),
        Choice(id="mode:home", title=home),
        Choice(id="mode:either", title=either),
    ]


def board_choices(boards: list[str]) -> list[Choice]:
    return [Choice(id=f"board:{b}", title=b) for b in boards]


def confirm_choices(lang: Lang) -> list[Choice]:
    yes, change = ("Haan, sahi hai", "Kuch badalna hai") if lang == "hi" else ("Confirm", "Change")
    return [Choice(id="confirm:yes", title=yes), Choice(id="confirm:change", title=change)]


def close_completed(when: ContactWhen, lang: Lang, start: str) -> str:
    return text(f"CLOSE_COMPLETED_{when.value}", lang, start=start)
