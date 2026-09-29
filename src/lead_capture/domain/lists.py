"""Allowed values from config/lists.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

from lead_capture.settings import ROOT

DEFAULT_LISTS_FILE = ROOT / "config" / "lists.yaml"


class AllowedLists(BaseModel):
    grade_levels: list[str]
    school_grade_levels: list[str]
    minor_grade_levels: list[str]
    boards: list[str]
    non_school_boards: list[str]
    subjects: list[str]
    subject_aliases: dict[str, str]
    cities: list[str]
    city_aliases: dict[str, str]
    ncr_pin_ranges: list[tuple[int, int]]
    modes: list[str]
    budget_units: list[str]
    relationships: list[str]
    guardian_relationships: list[str]
    goals: list[str]
    lead_statuses: list[str]

    @model_validator(mode="after")
    def _consistent(self) -> AllowedLists:
        for sub in (self.school_grade_levels, self.minor_grade_levels):
            if not set(sub) <= set(self.grade_levels):
                raise ValueError("school/minor grade levels must be a subset of grade_levels")
        for alias, target in self.subject_aliases.items():
            if target not in self.subjects:
                raise ValueError(f"subject alias {alias!r} points to unknown subject {target!r}")
        return self

    def for_sheet(self) -> dict[str, list[str]]:
        return {
            "Class / Level": self.grade_levels,
            "Board": self.boards + self.non_school_boards,
            "Subjects": self.subjects,
            "City": self.cities,
            "Mode": self.modes,
            "Budget Unit": [u.replace("_", " ") for u in self.budget_units],
            "Status": self.lead_statuses,
        }


def load_lists(path: Path | str | None = None) -> AllowedLists:
    return AllowedLists.model_validate(yaml.safe_load(Path(path or DEFAULT_LISTS_FILE).read_text()))


@lru_cache(maxsize=1)
def get_lists() -> AllowedLists:
    return load_lists()
