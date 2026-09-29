"""Requirement state: validation and normalisation of every captured value (data-model.md).

The model's extraction is only a proposal; ``RequirementState.apply`` decides what is stored.
Constitution Principle II — nothing reaches the lead register without passing through here.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, EmailStr, Field, TypeAdapter

from lead_capture.domain.lists import AllowedLists

OUT_OF_AREA = "out_of_area"
MAX_START_DAYS = 180

# Order in which missing required fields are asked (data-model.md "Missing-field order").
REQUIRED_ORDER: tuple[str, ...] = (
    "contact_name",
    "relationship",
    "student_name",
    "grade_level",
    "board",
    "subjects",
    "mode",
    "area",
    "city",
    "schedule",
    "start_date",
    "budget_min",
    "budget_unit",
    "guardian_name",
    "guardian_relationship",
)
OPTIONAL_FIELDS: tuple[str, ...] = (
    "goal",
    "sessions_per_week",
    "tutor_preferences",
    "level_notes",
    "email",
    "pincode",
)

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
_GRADE_ALIASES = {
    "ug": "Undergraduate",
    "undergrad": "Undergraduate",
    "college": "Undergraduate",
    "graduation": "Undergraduate",
    "pg": "Postgraduate",
    "postgrad": "Postgraduate",
    "masters": "Postgraduate",
    "adult": "Adult",
}
_ASAP = {"asap", "immediately", "now", "right away", "as soon as possible", "abhi", "turant"}
_EMAIL = TypeAdapter(EmailStr)


class InvalidValue(ValueError):
    pass


def _text(value: Any, lo: int, hi: int) -> str:
    text = str(value).strip()
    if not lo <= len(text) <= hi:
        raise InvalidValue(f"must be {lo}–{hi} characters")
    return text


def _one_of(value: Any, allowed: list[str], aliases: dict[str, str] | None = None) -> str:
    key = str(value).strip().lower().replace("_", " ")
    for option in allowed:
        if option.lower().replace("_", " ") == key:
            return option
    if aliases and key in aliases:
        return aliases[key]
    raise InvalidValue(f"not one of {allowed}")


def _grade(value: Any, lists: AllowedLists) -> str:
    raw = str(value).strip().lower()
    for option in lists.grade_levels:
        if option.lower() == raw:
            return option
    if raw in _GRADE_ALIASES:
        return _GRADE_ALIASES[raw]
    m = re.fullmatch(r"(?:class|std\.?|standard|grade)?\s*(\d{1,2}|[ivx]+)\s*(?:st|nd|rd|th)?", raw)
    if m:
        token = m.group(1)
        n = int(token) if token.isdigit() else _ROMAN.get(token)
        if n and 1 <= n <= 12:
            return f"Class {n}"
    raise InvalidValue("unknown class/level")


def _subjects(value: Any, lists: AllowedLists) -> list[str]:
    items = value if isinstance(value, list) else re.split(r",|\band\b|&|/", str(value))
    out: list[str] = []
    unknown: list[str] = []
    for item in (str(i).strip() for i in items):
        if not item:
            continue
        try:
            subject = _one_of(item, lists.subjects, lists.subject_aliases)
        except InvalidValue:
            unknown.append(item)
            continue
        if subject not in out:
            out.append(subject)
    if unknown:
        raise InvalidValue(f"unknown subject(s): {', '.join(unknown)}")
    if not 1 <= len(out) <= 5:
        raise InvalidValue("1–5 subjects")
    return out


def _positive_int(value: Any) -> int:
    try:
        n = int(str(value).replace(",", "").replace("₹", "").strip())
    except ValueError:
        raise InvalidValue("must be a whole number") from None
    if n <= 0:
        raise InvalidValue("must be positive")
    return n


def _budget_unit(value: Any) -> str:
    key = str(value).strip().lower().replace("_", " ").replace("-", " ")
    if key in {"per hour", "hourly", "hour", "an hour", "/hr", "per hr"}:
        return "per_hour"
    if key in {"per month", "monthly", "month", "a month", "/month", "per mo"}:
        return "per_month"
    raise InvalidValue("per_hour or per_month")


def _start_date(value: Any, today: date) -> str:
    raw = str(value).strip()
    if raw.lower() in _ASAP:
        return "ASAP"
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        raise InvalidValue("ASAP or YYYY-MM-DD") from None
    if not today <= d <= today + timedelta(days=MAX_START_DAYS):
        raise InvalidValue(f"must be between today and {MAX_START_DAYS} days ahead")
    return d.isoformat()


def _pincode_in_ncr(pin: str, lists: AllowedLists) -> bool:
    n = int(pin)
    return any(lo <= n <= hi for lo, hi in lists.ncr_pin_ranges)


class RequirementState(BaseModel):
    """Validated values captured so far. Every field is optional until the summary."""

    contact_name: str | None = None
    relationship: str | None = None
    student_name: str | None = None
    grade_level: str | None = None
    board: str | None = None
    subjects: list[str] = Field(default_factory=list)
    mode: str | None = None
    area: str | None = None
    city: str | None = None
    pincode: str | None = None
    schedule: str | None = None
    start_date: str | None = None
    budget_min: int | None = None
    budget_max: int | None = None
    budget_unit: str | None = None
    goal: str | None = None
    sessions_per_week: int | None = None
    tutor_preferences: str | None = None
    level_notes: str | None = None
    email: str | None = None
    guardian_name: str | None = None
    guardian_relationship: str | None = None
    out_of_area: bool = False  # a home-tuition location outside Delhi/NCR was given

    # ------------------------------------------------------------------ apply
    def apply(
        self, proposed: dict[str, Any], lists: AllowedLists, today: date
    ) -> tuple[RequirementState, dict[str, str]]:
        """Validate proposed values; return the new state and {field: reason} for rejects.

        Latest valid value wins. Invalid values never overwrite stored ones.
        """
        s = self.model_copy(deep=True)
        rejected: dict[str, str] = {}
        values = {k: v for k, v in proposed.items() if v is not None and hasattr(s, k)}
        values.pop("out_of_area", None)

        # mode first: city/pincode rules depend on it
        order = ["relationship", "mode"] + [k for k in values if k not in ("relationship", "mode")]
        for key in order:
            if key not in values:
                continue
            try:
                s._set(key, values[key], lists, today, provided=values)
            except InvalidValue as exc:
                rejected[key] = str(exc)

        s._derive(lists)
        return s, rejected

    def _set(self, key: str, value: Any, lists: AllowedLists, today: date, provided: dict) -> None:
        if key in ("contact_name", "student_name", "guardian_name"):
            setattr(self, key, _text(value, 1, 60))
        elif key == "relationship":
            self.relationship = _one_of(value, lists.relationships)
        elif key == "guardian_relationship":
            self.guardian_relationship = _one_of(value, lists.guardian_relationships)
        elif key == "grade_level":
            self.grade_level = _grade(value, lists)
        elif key == "board":
            self.board = _one_of(
                value, lists.boards + lists.non_school_boards, {"state board": "State"}
            )
        elif key == "subjects":
            self.subjects = _subjects(value, lists)
        elif key == "mode":
            self.mode = _one_of(value, lists.modes)
        elif key == "area":
            self.area = _text(value, 2, 80)
        elif key == "city":
            self._set_city(value, lists, provided)
        elif key == "pincode":
            self._set_pincode(value, lists)
        elif key == "schedule":
            self.schedule = _text(value, 3, 120)
        elif key == "start_date":
            self.start_date = _start_date(value, today)
        elif key == "budget_min":
            self.budget_min = _positive_int(value)
            if "budget_max" not in provided:
                self.budget_max = self.budget_min
        elif key == "budget_max":
            n = _positive_int(value)
            if self.budget_min is not None and n < self.budget_min:
                raise InvalidValue("budget_max must be ≥ budget_min")
            self.budget_max = n
        elif key == "budget_unit":
            self.budget_unit = _budget_unit(value)
        elif key == "goal":
            self.goal = _text(value, 1, 120)
        elif key == "sessions_per_week":
            n = _positive_int(value)
            if n > 7:
                raise InvalidValue("1–7 sessions per week")
            self.sessions_per_week = n
        elif key == "tutor_preferences":
            self.tutor_preferences = _text(value, 1, 200)
        elif key == "level_notes":
            self.level_notes = _text(value, 1, 300)
        elif key == "email":
            try:
                self.email = str(_EMAIL.validate_python(str(value).strip()))
            except ValueError:
                raise InvalidValue("not a valid email") from None

    def _set_city(self, value: Any, lists: AllowedLists, provided: dict) -> None:
        try:
            self.city = _one_of(value, lists.cities, lists.city_aliases)
            self.out_of_area = False
            return
        except InvalidValue:
            pass
        if self.mode == "online":
            return  # location irrelevant for online tuition
        if self.mode == "either":
            self._switch_to_online()
            return
        self.out_of_area = True
        raise InvalidValue(OUT_OF_AREA)

    def _set_pincode(self, value: Any, lists: AllowedLists) -> None:
        pin = str(value).strip().replace(" ", "")
        if not re.fullmatch(r"\d{6}", pin):
            raise InvalidValue("must be 6 digits")
        if self.mode != "online" and not _pincode_in_ncr(pin, lists):
            if self.mode == "either":
                self._switch_to_online()
                return
            self.out_of_area = True
            raise InvalidValue(OUT_OF_AREA)
        self.pincode = pin

    def _switch_to_online(self) -> None:
        self.mode = "online"
        self.area = self.city = self.pincode = None
        self.out_of_area = False

    def _derive(self, lists: AllowedLists) -> None:
        if self.relationship == "student" and self.contact_name and not self.student_name:
            self.student_name = self.contact_name
        if (
            self.grade_level
            and self.grade_level not in lists.school_grade_levels
            and self.board not in lists.non_school_boards
        ):
            self.board = "N/A"
        if self.budget_min is not None and self.budget_max is None:
            self.budget_max = self.budget_min
        if self.mode == "online":
            # location is not needed for online tuition — don't keep it (store only what's needed)
            self.area = self.city = self.pincode = None
            self.out_of_area = False

    # ------------------------------------------------------------- queries
    def is_minor_alone(self, lists: AllowedLists) -> bool:
        return self.relationship == "student" and self.grade_level in lists.minor_grade_levels

    def missing_required(self, minor_alone: bool = False) -> list[str]:
        missing: list[str] = []
        for key in REQUIRED_ORDER:
            if key in ("guardian_name", "guardian_relationship") and not minor_alone:
                continue
            if key in ("area", "city") and self.mode == "online":
                continue
            if key == "board" and self.board:
                continue
            value = getattr(self, key)
            if value in (None, [], ""):
                missing.append(key)
        return missing

    def is_complete(self, minor_alone: bool = False) -> bool:
        return not self.missing_required(minor_alone)

    def captured(self) -> dict[str, Any]:
        """Validated values only (what the model sees as state)."""
        return {
            k: v
            for k, v in self.model_dump().items()
            if k != "out_of_area" and v not in (None, [], "")
        }
