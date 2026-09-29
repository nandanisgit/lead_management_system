"""Post-generation checks on model replies (contracts/llm-extraction.md). Limits from settings."""

from __future__ import annotations

import re

from lead_capture.settings import ConversationSettings

_CURRENCY = re.compile(
    r"(₹\s*[\d,]+|\brs\.?\s*[\d,]+|\binr\s*[\d,]+|[\d,]+\s*(?:rs\b|rupees|rupaye|/-))", re.I
)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_HINDI_WORDS = re.compile(
    r"\b(hai|hain|aap|aapka|aapke|kya|ke|ka|ki|se|mein|kaunsi|kaunse|kitna|chahiye|batayein|"
    r"bataiye|dhanyavaad|namaste|theek|zaroor|kab)\b",
    re.I,
)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)}


def problems(
    reply: str,
    *,
    tutee_texts: list[str],
    language: str,
    limits: ConversationSettings,
) -> list[str]:
    found: list[str] = []
    if not reply.strip():
        return ["empty"]
    questions = reply.count("?") + reply.count("？")
    if questions > limits.max_questions_per_message:
        found.append("too_many_questions")
    if len(reply.split()) > limits.max_words_per_message:
        found.append("too_long")
    stated = set().union(*(_numbers(t) for t in tutee_texts)) if tutee_texts else set()
    for match in _CURRENCY.finditer(reply):
        if not _numbers(match.group(0)) <= stated:
            found.append("suggested_amount")
            break
    has_devanagari = bool(_DEVANAGARI.search(reply))
    hindi_words = len(_HINDI_WORDS.findall(reply))
    if language == "hi" and not has_devanagari and hindi_words < 2:
        found.append("wrong_language")
    if language == "en" and (has_devanagari or hindi_words >= 4):
        found.append("wrong_language")
    return found
