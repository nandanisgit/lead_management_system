"""Grounding: keep only model-proposed values the tutee actually said (constitution II).

Why: validation checks that a value has the right *form* (a real class, a real board), not
that the tutee *said* it. Small models in particular invent plausible details ("Monday and
Wednesday", "Class 8") when a message is vague. Every proposed value must therefore be
traceable to the tutee's own recent messages — the value itself, one of its labels or
aliases from config/requirement.yaml, or its number — or it is dropped. Generic per field
*type*: no field name appears here.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from lead_capture.domain import field_types
from lead_capture.domain.field_types import InvalidValue
from lead_capture.domain.schema import FieldSpec, RequirementSchema

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
# words too common to show that a free-text value came from the tutee
_FILLER = {"and", "the", "for", "with", "per", "from", "any", "all"}
_MIN_WORD = 3  # shorter tokens ("pm", "to") prove nothing on their own
# types checked against the tutee's text as typed (digits with separators, @ and dots)
_RAW_TEXT_KINDS = ("email_address", "phone_number", "postal_code", "positive_int", "int_range")


def _norm(text: str) -> str:
    """Lower-case, single-spaced words only (punctuation and emoji dropped)."""
    return " ".join(_WORD.findall(str(text).lower()))


def _said(phrase: str, corpus: str) -> bool:
    """Whether ``phrase`` appears as whole word(s) in the tutee's normalised text."""
    phrase = _norm(phrase)
    return bool(phrase) and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", corpus) is not None


def _numbers(corpus: str) -> set[int]:
    """Every number the tutee wrote (digits, ignoring separators like 6,000)."""
    return {int(n) for n in re.findall(r"\d+", corpus.replace(",", ""))}


def _option_phrases(spec: FieldSpec, schema: RequirementSchema, value: str) -> list[str]:
    """Ways a tutee may say a choice value: itself, its labels, aliases, number words."""
    phrases = [value]
    for labels in [*spec.option_labels.values(), *spec.button_labels.values()]:
        if value in labels:
            phrases.append(labels[value])
    phrases += [alias for alias, target in schema.aliases(spec.name).items() if target == value]
    if spec.numbered:
        match = re.search(r"\d+", value)
        if match:
            n = int(match.group())
            phrases += [str(n), f"{n}st", f"{n}nd", f"{n}rd", f"{n}th"]
            words = schema.lists.get(spec.numbered.words or "", {}) or {}
            phrases += [w for w, num in words.items() if int(num) == n]
    return phrases


def _choice_said(spec, schema, raw, corpus: str) -> bool:
    """A choice value is grounded if the tutee said it, a label, an alias or its number."""
    if _said(str(raw), corpus):
        return True
    try:
        value = field_types.normalise(
            spec, [raw] if spec.type == "multi_choice" else raw, schema, date.today()
        )
    except InvalidValue:
        return False  # invalid values are rejected by validation anyway
    if isinstance(value, list):  # one item of a multi-choice field
        value = value[0] if value else ""
    return any(_said(p, corpus) for p in _option_phrases(spec, schema, str(value)))


def _text_said(raw: Any, corpus: str) -> bool:
    """Free text is grounded when most of its meaningful words come from the tutee."""
    words = [w for w in _norm(str(raw)).split() if len(w) >= _MIN_WORD and w not in _FILLER]
    if not words:  # e.g. "6-8": fall back to its numbers
        nums = {int(n) for n in re.findall(r"\d+", str(raw))}
        return bool(nums) and nums <= _numbers(corpus)
    found = sum(1 for w in words if w in corpus)  # substring: "weekday" in "weekdays"
    return found * 2 >= len(words)


def _supported(spec: FieldSpec, schema: RequirementSchema, raw: Any, corpus: str) -> Any:
    """The grounded part of a proposed value, or None when nothing of it was said."""
    kind = spec.type
    if kind == "text":
        return raw if _text_said(raw, corpus) else None
    if kind in ("choice", "grade"):
        return raw if _choice_said(spec, schema, raw, corpus) else None
    if kind == "multi_choice":
        items = raw if isinstance(raw, list) else [raw]
        kept = [i for i in items if _choice_said(spec, schema, i, corpus)]
        return kept or None
    if kind in ("positive_int", "int_range"):
        digits = re.sub(r"[^\d]", "", str(raw))
        return raw if digits and int(digits) in _numbers(corpus) else None
    if kind == "date_or_asap":
        text = str(raw).strip()
        asap = [spec.asap_value, *schema.lists[spec.asap_words]]
        if text.lower() == spec.asap_value.lower():
            return raw if any(_said(w, corpus) for w in asap) else None
        day = re.search(r"\d{4}-\d{2}-(\d{2})", text)
        return raw if day and int(day.group(1)) in _numbers(corpus) else None
    if kind in ("phone_number", "postal_code"):
        digits = re.sub(r"\D", "", str(raw))
        tail = digits[-(spec.national_digits or spec.digits or len(digits)) :]
        return raw if tail and tail in re.sub(r"\D", "", corpus) else None
    if kind == "email_address":
        return raw if str(raw).strip().lower() in corpus.replace(" ", "") else None
    return raw


def grounded(
    schema: RequirementSchema, proposed: dict[str, Any], tutee_texts: list[str]
) -> tuple[dict[str, Any], list[str]]:
    """Split proposed values into those the tutee said and the names of those they didn't."""
    corpus = _norm(" ".join(tutee_texts))
    raw_corpus = " ".join(tutee_texts).lower()
    kept: dict[str, Any] = {}
    dropped: list[str] = []
    for name, raw in proposed.items():
        spec = schema.fields.get(name)
        if spec is None or raw in (None, "", []):
            continue
        text = raw_corpus if spec.type in _RAW_TEXT_KINDS else corpus
        value = _supported(spec, schema, raw, text)
        if value is None:
            dropped.append(name)
        else:
            kept[name] = value
    return kept, dropped
