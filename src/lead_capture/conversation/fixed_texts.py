"""Fixed texts the assistant sends without a model call — loaded from config.

Why: deterministic turns (button taps, consent, summary, closing) don't need the model
(cost saving, research R16), and every model reply needs a safe fallback when it fails the
guards. The copy lives in config/messages.yaml and the field questions in
config/requirement.yaml, so wording and fields change without code changes.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from lead_capture.domain.hours import ContactWhen
from lead_capture.domain.schema import RequirementSchema
from lead_capture.domain.templates import render
from lead_capture.ports.channel import Choice, OutboundMessage


class _Strict(BaseModel):
    """Base for config models: unknown keys in messages.yaml are errors."""

    model_config = ConfigDict(extra="forbid")


class HindiMarkers(_Strict):
    """Signals that text is Hindi/Hinglish (see config/messages.yaml → language.hindi)."""

    script_range: str
    tutee_markers: list[str]
    reply_markers: list[str]
    min_tutee_markers: int
    min_reply_markers: int
    max_markers_in_english_reply: int


class LanguageConfig(_Strict):
    """Language detection settings."""

    default: str
    hindi: HindiMarkers


class CurrencyConfig(_Strict):
    """Money markers the guards look for (FR-006)."""

    before_amount: list[str]
    after_amount: list[str]


class Messages(_Strict):
    """Everything in config/messages.yaml."""

    texts: dict[str, dict[str, str]]
    time_display_format: str
    choices: dict[str, list[dict[str, str]]]
    language: LanguageConfig
    currency: CurrencyConfig

    def words_pattern(self, words: list[str]) -> re.Pattern:
        """Whole-word, case-insensitive pattern for a list of marker words."""
        return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)


def load_messages(path: Path | str) -> Messages:
    """Load and validate a messages file."""
    return Messages.model_validate(yaml.safe_load(Path(path).read_text()))


@lru_cache(maxsize=4)
def _cached(path: str) -> Messages:
    """Load a messages file once per path."""
    return load_messages(path)


def get_messages() -> Messages:
    """The messages file named in settings, loaded once per process."""
    from lead_capture.settings import ROOT, get_settings

    return _cached(str(ROOT / get_settings().schema_files.messages_file))


# ---------------------------------------------------------------- texts
def text(key: str, lang: str = "en", **ctx: Any) -> str:
    """A fixed text in ``lang`` (falls back to English), with placeholders filled."""
    variants = get_messages().texts[key]
    return render(variants.get(lang) or variants["en"], ctx)


def keys() -> list[str]:
    """All fixed-text keys (used by tests that check every text obeys the limits)."""
    return list(get_messages().texts)


def guess_language(message: str | None) -> str:
    """Local Hindi/English guess for a tutee message.

    Used before consent, when no model call is allowed yet.
    """
    msgs = get_messages()
    hindi = msgs.language.hindi
    if not message:
        return msgs.language.default
    if re.search(f"[{hindi.script_range}]", message):
        return "hi"
    found = msgs.words_pattern(hindi.tutee_markers).findall(message)
    return "hi" if len(found) >= hindi.min_tutee_markers else msgs.language.default


# ---------------------------------------------------------------- field questions
def ask_text(fields: list[str], lang: str, schema: RequirementSchema, values: dict) -> str:
    """The question for the next missing field(s).

    Uses the group question when the whole group is asked, otherwise each field's own
    question, and a generic fallback when none is configured.
    """
    ctx = {name: schema.display(name, value, lang) for name, value in values.items()}
    for group in schema.ask_groups:
        if group.fields == fields and group.ask:
            return render(group.ask.get(lang) or group.ask["en"], ctx)
    parts = []
    for name in fields:
        ask = schema.fields[name].ask
        if ask:
            parts.append(render(ask.get(lang) or ask["en"], ctx))
    return " ".join(parts) or text("ASK_GENERIC", lang)


def clarify_text(fields: list[str], lang: str, schema: RequirementSchema) -> str:
    """Ask the tutee to re-check values that failed validation, named by their labels."""
    labels = ", ".join(schema.label(name, lang) for name in fields)
    return text("CLARIFY", lang, fields=labels)


def field_choices(name: str, lang: str, schema: RequirementSchema) -> list[Choice]:
    """Tap options for a field asked on its own (from its ``buttons`` lists), or []."""
    spec = schema.fields[name]
    labels = spec.button_labels.get(lang) or spec.button_labels.get("en") or {}
    return [
        Choice(id=f"{name}:{value}", title=labels.get(value, value))
        for value in schema.button_options(name)
    ]


def choices(kind: str, lang: str) -> list[Choice]:
    """Tap options that are not field values (consent, confirm) from config."""
    return [Choice(id=c["id"], title=c.get(lang) or c["en"]) for c in get_messages().choices[kind]]


def choice_prefixes(schema: RequirementSchema) -> tuple[str, ...]:
    """Every tap-id prefix the engine understands: consent/confirm plus button fields."""
    fixed = tuple(f"{kind}:" for kind in get_messages().choices)
    fields = tuple(f"{name}:" for name, spec in schema.fields.items() if spec.buttons)
    return fixed + fields


def with_choices(message_text: str, options: list[Choice], lang: str) -> OutboundMessage:
    """A reply with tap options, including the list labels channels show for long lists."""
    return OutboundMessage(
        text=message_text,
        choices=options,
        list_button=text("LIST_BUTTON", lang) if options else None,
        list_section=text("LIST_SECTION", lang) if options else None,
    )


def display_time(at) -> str:
    """A time as tutees see it (config: time_display_format), e.g. "10 AM"."""
    return at.strftime(get_messages().time_display_format)


def close_completed(when: ContactWhen, lang: str, start: str) -> str:
    """Closing message saying when the operations team will get in touch (FR-018)."""
    return text(f"CLOSE_COMPLETED_{when.value}", lang, start=start)
