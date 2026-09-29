"""Summary shown to the tutee and the LeadRow written to the sheet — both built from validated
values only (constitution Principle II)."""

from __future__ import annotations

from datetime import datetime

from lead_capture.conversation import fixed_texts as ft
from lead_capture.domain.hours import format_ist
from lead_capture.domain.requirement import RequirementState
from lead_capture.ports.leads import LeadRow

_UNIT = {"per_hour": "per hour", "per_month": "per month"}
_MODE = {
    "en": {"online": "Online", "home": "Home tuition", "either": "Online or home"},
    "hi": {"online": "Online", "home": "Ghar par tuition", "either": "Online ya ghar par"},
}


def _budget(s: RequirementState) -> str:
    unit = _UNIT.get(s.budget_unit or "", "")
    if s.budget_min == s.budget_max:
        return f"₹{s.budget_min} {unit}".strip()
    return f"₹{s.budget_min}–{s.budget_max} {unit}".strip()


def summary_text(s: RequirementState, lang: str, minor_alone: bool) -> str:
    board = f" {s.board}" if s.board and s.board != "N/A" else ""
    mode = _MODE.get(lang, _MODE["en"]).get(s.mode or "", s.mode or "")
    where = f" — {s.area}, {s.city}" if s.mode != "online" and s.area and s.city else ""
    start = "ASAP" if s.start_date == "ASAP" else s.start_date
    lines = [
        ft.text("SUMMARY_LEAD_IN", lang),
        f"• {s.student_name}, {s.grade_level}{board}",
        f"• {', '.join(s.subjects)}",
        f"• {mode}{where}",
        f"• {s.schedule}; start {start}",
        f"• Budget {_budget(s)}",
    ]
    if minor_alone and s.guardian_name:
        lines.append(f"• Parent/guardian: {s.guardian_name} ({s.guardian_relationship})")
    lines.append("")
    if minor_alone:
        lines.append(ft.text("SUMMARY_MINOR", lang))
    lines.append(ft.text("SUMMARY_CONFIRM", lang))
    return "\n".join(lines)


def minor_marker(s: RequirementState) -> str:
    return (
        f"MINOR – consent given by student – contact parent/guardian: "
        f"{s.guardian_name} ({s.guardian_relationship})"
    )


def lead_row(
    *,
    lead_id: str,
    now: datetime,
    timezone: str,
    wa_number: str,
    consent_at: datetime,
    language: str,
    source: str,
    state: RequirementState,
    minor_alone: bool,
) -> LeadRow:
    notes = [minor_marker(state)] if minor_alone else []
    if state.level_notes:
        notes.append(state.level_notes)
    if state.email:
        notes.append(f"Email: {state.email}")
    online = state.mode == "online"
    return LeadRow(
        lead_id=lead_id,
        created_at=format_ist(now, timezone),
        whatsapp_number=wa_number,
        contact_name=state.contact_name or "",
        relationship=state.relationship or "",
        student_name=state.student_name or "",
        grade_level=state.grade_level or "",
        board=state.board or "",
        subjects=", ".join(state.subjects),
        mode=state.mode or "",
        area="" if online else (state.area or ""),
        city="" if online else (state.city or ""),
        pincode=state.pincode or "",
        schedule=state.schedule or "",
        start_date=state.start_date or "",
        budget_min=state.budget_min or 0,
        budget_max=state.budget_max or 0,
        budget_unit=_UNIT.get(state.budget_unit or "", ""),
        goal=state.goal or "",
        sessions_per_week=str(state.sessions_per_week or ""),
        tutor_preferences=state.tutor_preferences or "",
        notes=" | ".join(notes),
        language="Hindi" if language == "hi" else "English",
        source=source,
        consent_at=format_ist(consent_at, timezone),
    )
