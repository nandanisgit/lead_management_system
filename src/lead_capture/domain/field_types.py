"""Validators for each field *type* named in config/requirement.yaml.

Why: validation rules are generic per type (text length, choice from a list, number range…)
and their parameters come from config, so no field name appears here. A new field reuses
one of these types; a genuinely new kind of value is the only reason to add code here.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import EmailStr, TypeAdapter

if TYPE_CHECKING:
    from lead_capture.domain.schema import FieldSpec, RequirementSchema

_EMAIL = TypeAdapter(EmailStr)
_ROMAN = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
    "xi": 11,
    "xii": 12,
}
_NUMBERED = re.compile(
    r"(?:class|std\.?|standard|grade)?\s*(\d{1,2}|[ivx]+)\s*(?:st|nd|rd|th)?", re.I
)
_LIST_SEPARATORS = re.compile(r",|\band\b|&|/")
# ITU-T E.164: a full international number has at most 15 digits; 8 is the practical minimum.
E164_MIN_DIGITS = 8
E164_MAX_DIGITS = 15


class InvalidValue(ValueError):
    """A proposed value failed validation; the message becomes the clarification reason."""


def _text(spec: FieldSpec, raw: Any) -> str:
    """Trimmed free text within the configured length."""
    text = str(raw).strip()
    if not spec.min_length <= len(text) <= spec.max_length:
        raise InvalidValue(f"must be {spec.min_length}–{spec.max_length} characters")
    return text


def _choice(spec: FieldSpec, raw: Any, schema: RequirementSchema) -> str:
    """One of the field's options, matched case-insensitively or through its aliases."""
    key = str(raw).strip().lower().replace("_", " ")
    for option in schema.options(spec.name):
        if option.lower().replace("_", " ") == key:
            return option
    aliases = schema.aliases(spec.name)
    if key in aliases:
        return aliases[key]
    raise InvalidValue("not one of the accepted values")


def _multi_choice(spec: FieldSpec, raw: Any, schema: RequirementSchema) -> list[str]:
    """Several options (list or "a, b and c"), de-duplicated, within the item limits."""
    items = raw if isinstance(raw, list) else _LIST_SEPARATORS.split(str(raw))
    out: list[str] = []
    unknown: list[str] = []
    for item in (str(i).strip() for i in items):
        if not item:
            continue
        try:
            value = _choice(spec, item, schema)
        except InvalidValue:
            unknown.append(item)
            continue
        if value not in out:
            out.append(value)
    if unknown:
        raise InvalidValue(f"unknown value(s): {', '.join(unknown)}")
    if not spec.min_items <= len(out) <= spec.max_items:
        raise InvalidValue(f"{spec.min_items}–{spec.max_items} items")
    return out


def _grade(spec: FieldSpec, raw: Any, schema: RequirementSchema) -> str:
    """A level from the list, an alias ("ug"), or a numbered level ("9th", "class IX")."""
    try:
        return _choice(spec, raw, schema)
    except InvalidValue:
        pass
    if spec.numbered:
        n = _level_number(spec, str(raw).strip().lower(), schema)
        if n and spec.numbered.min <= n <= spec.numbered.max:
            value = spec.numbered.format.format(n=n)
            if value in schema.options(spec.name):
                return value
    raise InvalidValue("unknown class/level")


def _level_number(spec: FieldSpec, text: str, schema: RequirementSchema) -> int | None:
    """The level number in "9th", "class IX", "1 class", "first standard", "pehli kaksha"."""
    match = _NUMBERED.fullmatch(text)
    if match:
        token = match.group(1)
        return int(token) if token.isdigit() else _ROMAN.get(token)
    words = re.findall(r"[^\W_]+", text)
    level_words = {w.lower() for w in spec.numbered.level_words}
    if not words or len(words) > 3 or not (set(words) & level_words or len(words) == 1):
        return None  # only short level phrases, e.g. not a whole sentence
    number_words = schema.lists.get(spec.numbered.words or "", {}) or {}
    for word in words:
        suffix = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", word)
        if suffix:
            return int(suffix.group(1))
        if word in number_words:
            return int(number_words[word])
    return None


def _int(raw: Any) -> int:
    """Whole number from text like "₹6,000"."""
    try:
        return int(re.sub(r"[^\d-]", "", str(raw)))
    except ValueError:
        raise InvalidValue("must be a whole number") from None


def _positive_int(spec: FieldSpec, raw: Any) -> int:
    """A whole number greater than zero."""
    n = _int(raw)
    if n <= 0:
        raise InvalidValue("must be positive")
    return n


def _int_range(spec: FieldSpec, raw: Any) -> int:
    """A whole number within the configured min–max."""
    n = _int(raw)
    if not spec.min <= n <= spec.max:
        raise InvalidValue(f"must be {spec.min}–{spec.max}")
    return n


def _date_or_asap(spec: FieldSpec, raw: Any, schema: RequirementSchema, today: date) -> str:
    """The ASAP value (from any configured ASAP word) or a date within the allowed window."""
    text = str(raw).strip()
    if text.lower() in {w.lower() for w in schema.lists[spec.asap_words]} or (
        text.lower() == spec.asap_value.lower()
    ):
        return spec.asap_value
    try:
        when = date.fromisoformat(text)
    except ValueError:
        raise InvalidValue(f"{spec.asap_value} or YYYY-MM-DD") from None
    if not today <= when <= today + timedelta(days=spec.max_days_ahead):
        raise InvalidValue(f"must be between today and {spec.max_days_ahead} days ahead")
    return when.isoformat()


def _email(spec: FieldSpec, raw: Any) -> str:
    """A syntactically valid email address."""
    try:
        return str(_EMAIL.validate_python(str(raw).strip()))
    except ValueError:
        raise InvalidValue("not a valid email") from None


def _pincode(spec: FieldSpec, raw: Any) -> str:
    """A postal code of exactly the configured number of digits."""
    pin = re.sub(r"\s", "", str(raw))
    if not re.fullmatch(rf"\d{{{spec.digits}}}", pin):
        raise InvalidValue(f"must be {spec.digits} digits")
    return pin


def _phone(spec: FieldSpec, raw: Any) -> str:
    """A phone number in international form, ``+<country code><number>``.

    Accepts spaces, dashes, brackets and dots; a leading ``+`` or ``00`` means the country
    code is included; a bare national number (optionally with a trunk ``0``) gets the
    configured default country code. International numbers are checked for E.164 length.
    """
    text = str(raw).strip()
    if not re.fullmatch(r"[+\d\s().\-]+", text):
        raise InvalidValue("not a phone number")
    digits = re.sub(r"\D", "", text)
    cc, national = spec.country_code, spec.national_digits
    if text.startswith("+") or digits.startswith("00"):
        full = digits[2:] if digits.startswith("00") and not text.startswith("+") else digits
    elif len(digits) == national:
        full = cc + digits
    elif len(digits) == national + 1 and digits.startswith("0"):
        full = cc + digits[1:]
    elif len(digits) == len(cc) + national and digits.startswith(cc):
        full = digits
    else:
        raise InvalidValue(f"must be a {national}-digit number")
    if full.startswith(cc) and len(full) != len(cc) + national:
        raise InvalidValue(f"must be a {national}-digit number")
    if not E164_MIN_DIGITS <= len(full) <= E164_MAX_DIGITS:
        raise InvalidValue("not a phone number")
    return "+" + full


def normalise(spec: FieldSpec, raw: Any, schema: RequirementSchema, today: date) -> Any:
    """Validate and normalise ``raw`` for ``spec``; raise InvalidValue with a reason."""
    kind = spec.type
    if kind == "text":
        return _text(spec, raw)
    if kind == "choice":
        return _choice(spec, raw, schema)
    if kind == "multi_choice":
        return _multi_choice(spec, raw, schema)
    if kind == "grade":
        return _grade(spec, raw, schema)
    if kind == "positive_int":
        return _positive_int(spec, raw)
    if kind == "int_range":
        return _int_range(spec, raw)
    if kind == "date_or_asap":
        return _date_or_asap(spec, raw, schema, today)
    if kind == "email_address":
        return _email(spec, raw)
    if kind == "postal_code":
        return _pincode(spec, raw)
    if kind == "phone_number":
        return _phone(spec, raw)
    raise InvalidValue(f"unsupported field type {kind}")


def in_service_area(spec: FieldSpec, value: Any, schema: RequirementSchema) -> bool:
    """For fields with ``service_area: {ranges: ...}``: is the value inside a range?"""
    if isinstance(spec.service_area, dict) and "ranges" in spec.service_area:
        n = int(value)
        return any(lo <= n <= hi for lo, hi in schema.lists[spec.service_area["ranges"]])
    return True
