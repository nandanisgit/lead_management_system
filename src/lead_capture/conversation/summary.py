"""The summary the tutee confirms and the lead row written to the sheet.

Why: both must show exactly the validated values (constitution Principle II), so they are
built by code — never by the model — from the layouts in config/requirement.yaml
(``summary:`` and ``sheet.leads``). Adding a field there adds it here automatically.
"""

from __future__ import annotations

from typing import Any

from lead_capture.conversation import fixed_texts as ft
from lead_capture.domain.requirement import Requirement
from lead_capture.domain.schema import RequirementSchema
from lead_capture.domain.templates import render


def display_context(schema: RequirementSchema, req: Requirement, context: str) -> dict[str, Any]:
    """Every field's value as people see it in ``context`` ("en", "hi" or "sheet")."""
    return {name: schema.display(name, req.get(name), context) for name in schema.fields}


def _derived(schema: RequirementSchema, req: Requirement, lang: str) -> dict[str, str]:
    """Placeholders built from several fields, e.g. the budget "₹500–800 per month"."""
    out: dict[str, str] = {}
    for key, spec in schema.summary.derived.items():
        low, high = req.get(spec.min), req.get(spec.max)
        if low is None:
            continue
        unit = schema.display(spec.unit, req.get(spec.unit), lang)
        template = spec.same if high in (None, low) else spec.range
        out[key] = render(template, {"min": low, "max": high, "unit": unit}).strip()
    return out


def summary_text(schema: RequirementSchema, req: Requirement, lang: str, minor_alone: bool) -> str:
    """Confirmation summary (FR-013) in the tutee's language, with the confirm question."""
    ctx = display_context(schema, req, lang) | _derived(schema, req, lang)
    lines = [ft.text("SUMMARY_LEAD_IN", lang)]
    for template in schema.summary.lines.get(lang) or schema.summary.lines["en"]:
        line = render(template, ctx).rstrip()
        if line.strip(" •"):
            lines.append(line)
    lines.append("")
    if minor_alone:
        lines.append(ft.text("SUMMARY_MINOR", lang))
    lines.append(ft.text("SUMMARY_CONFIRM", lang))
    return "\n".join(lines)


def lead_values(
    schema: RequirementSchema, req: Requirement, meta: dict[str, Any], minor_alone: bool
) -> list[Any]:
    """Values for the bot-owned columns of the Leads tab, in configured column order.

    ``meta`` carries non-field values (lead_id, created_at, whatsapp_number, language,
    source, consent_at). Status comes from config; the minor marker only for FR-029 leads.
    """
    sheet = schema.sheet
    fields = display_context(schema, req, "sheet")
    meta = {
        **meta,
        "status": sheet.initial_status,
        "language": sheet.language_labels.get(meta.get("language", ""), meta.get("language")),
        "minor_marker": render(sheet.minor_marker, fields) if minor_alone else "",
    }
    ctx = fields | meta
    row: list[Any] = []
    for col in sheet.leads.columns:
        if col.owner == "ops":
            break
        if col.value:
            kind, _, name = col.value.partition(".")
            row.append(fields[name] if kind == "field" else meta.get(name, ""))
        else:
            parts = [render(p, ctx).strip() for p in col.parts or []]
            row.append(col.separator.join(p for p in parts if p))
    return row
