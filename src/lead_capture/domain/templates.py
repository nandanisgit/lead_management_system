"""Tiny template renderer for config-driven texts (questions, summaries, sheet notes).

Why: user-facing copy and sheet formats live in YAML (config/requirement.yaml,
config/messages.yaml) instead of code, and they need two things plain ``str.format`` lacks —
a fallback when a value is missing, and parts that disappear when their value is missing
(e.g. "Hi[ {name}]!" → "Hi!" when the name is unknown).

Syntax:
    {key}            value of ``key`` ("" when missing)
    {key|default}    value of ``key``, or ``default`` when missing
    [ ... ]          optional part: dropped if any ``{key}`` inside it (without default) is empty
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_OPTIONAL = re.compile(r"\[([^\[\]]*)\]")
_PLACEHOLDER = re.compile(r"\{(\w+)(?:\|([^{}]*))?\}")


def _is_empty(value: Any) -> bool:
    """Treat None, empty strings and empty lists as "no value" (so optional parts drop)."""
    return value is None or value == "" or value == []


def _fill(text: str, ctx: Mapping[str, Any]) -> tuple[str, bool]:
    """Substitute placeholders; also report whether any placeholder without default was empty."""
    missing = False

    def sub(match: re.Match) -> str:
        """Replace one placeholder, noting when it had no value and no default."""
        nonlocal missing
        value = ctx.get(match.group(1))
        if _is_empty(value):
            if match.group(2) is not None:
                return match.group(2)
            missing = True
            return ""
        return str(value)

    return _PLACEHOLDER.sub(sub, text), missing


def render(template: str, ctx: Mapping[str, Any]) -> str:
    """Render ``template`` with ``ctx``, dropping optional parts whose values are missing."""

    def optional(match: re.Match) -> str:
        """Render an optional [ ... ] part, or drop it if a value inside is missing."""
        filled, missing = _fill(match.group(1), ctx)
        return "" if missing else filled

    return _fill(_OPTIONAL.sub(optional, template), ctx)[0]


def placeholders(template: str) -> set[str]:
    """Names a template refers to — used to validate config templates at start-up."""
    return {m.group(1) for m in _PLACEHOLDER.finditer(template)}
