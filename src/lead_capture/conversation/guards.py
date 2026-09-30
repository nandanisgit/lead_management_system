"""Post-generation checks on model replies (contracts/llm-extraction.md).

Why: the model phrases replies, but some rules are non-negotiable — at most N questions and
M words (FR-001), the tutee's language (FR-002), and never introducing a fee or budget
amount (FR-006). A reply that breaks one is regenerated or replaced by fixed text. Limits
come from settings; language and currency markers from config/messages.yaml.
"""

from __future__ import annotations

import re

from lead_capture.conversation.fixed_texts import Messages, get_messages
from lead_capture.settings import ConversationSettings


def _numbers(text: str) -> set[str]:
    """Digits in a text, commas removed ("6,000" → "6000")."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)}


def _currency_pattern(msgs: Messages) -> re.Pattern:
    """Amount written with a currency marker before or after it."""
    before = "|".join(re.escape(m) for m in msgs.currency.before_amount)
    after = "|".join(re.escape(m) for m in msgs.currency.after_amount)
    return re.compile(rf"((?:{before})\s*[\d,]+|[\d,]+\s*(?:{after}))", re.I)


def problems(
    reply: str,
    *,
    tutee_texts: list[str],
    language: str,
    limits: ConversationSettings,
) -> list[str]:
    """Rule violations in ``reply`` (empty list = OK to send).

    ``tutee_texts`` are the tutee's own messages: an amount they stated may be repeated back.
    ``language`` is the tutee's language ("en"/"hi"); any other value skips the language check.
    """
    msgs = get_messages()
    hindi = msgs.language.hindi
    found: list[str] = []
    if not reply.strip():
        return ["empty"]
    if reply.count("?") + reply.count("？") > limits.max_questions_per_message:
        found.append("too_many_questions")
    if len(reply.split()) > limits.max_words_per_message:
        found.append("too_long")
    stated = set().union(*(_numbers(t) for t in tutee_texts)) if tutee_texts else set()
    for match in _currency_pattern(msgs).finditer(reply):
        if not _numbers(match.group(0)) <= stated:
            found.append("suggested_amount")
            break
    has_script = bool(re.search(f"[{hindi.script_range}]", reply))
    markers = len(msgs.words_pattern(hindi.reply_markers).findall(reply))
    if language == "hi" and not has_script and markers < hindi.min_reply_markers:
        found.append("wrong_language")
    if language == "en" and (has_script or markers > hindi.max_markers_in_english_reply):
        found.append("wrong_language")
    return found
