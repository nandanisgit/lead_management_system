"""LeadRepository port — Google Sheet today, database or CRM later (contracts/lead-sheet.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def guard(value: Any) -> Any:
    """Formula-injection guard: text starting with = + - @ is stored as literal text."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


class LeadRow(BaseModel):
    """Columns A–Z of the Leads tab, in order. AA–AC belong to operations and are never written."""

    lead_id: str  # A
    created_at: str  # B  YYYY-MM-DD HH:MM IST
    whatsapp_number: str  # C
    contact_name: str  # D
    relationship: str  # E
    student_name: str  # F
    grade_level: str  # G
    board: str  # H
    subjects: str  # I  comma-separated
    mode: str  # J
    area: str = ""  # K
    city: str = ""  # L
    pincode: str = ""  # M
    schedule: str  # N
    start_date: str  # O
    budget_min: int  # P
    budget_max: int  # Q
    budget_unit: str  # R  "per hour" / "per month"
    goal: str = ""  # S
    sessions_per_week: str = ""  # T
    tutor_preferences: str = ""  # U
    notes: str = ""  # V
    language: str  # W  English / Hindi
    source: str  # X
    consent_at: str  # Y
    status: str = "NEW"  # Z

    def to_values(self) -> list[Any]:
        return [guard(v) for v in self.model_dump().values()]


LEAD_HEADERS: tuple[str, ...] = (
    "Lead ID",
    "Created At",
    "WhatsApp Number",
    "Contact Name",
    "Relationship",
    "Student Name",
    "Class / Level",
    "Board",
    "Subjects",
    "Mode",
    "Area",
    "City",
    "PIN Code",
    "Preferred Schedule",
    "Start Date",
    "Budget Min (₹)",
    "Budget Max (₹)",
    "Budget Unit",
    "Goal",
    "Sessions per Week",
    "Tutor Preferences",
    "Notes",
    "Language",
    "Source",
    "Consent At",
    "Status",
    "Assigned To",
    "Ops Notes",
    "Last Updated",
)


class HandoffRow(BaseModel):
    """Columns A–H of the Handoffs tab. Column I (Resolved) belongs to operations."""

    handoff_id: str  # A
    time: str  # B
    whatsapp_number: str  # C
    name: str  # D
    reason: str  # E
    captured_so_far: str  # F
    lead_id: str = ""  # G
    reply_by: str  # H

    def to_values(self) -> list[Any]:
        return [guard(v) for v in self.model_dump().values()]


HANDOFF_HEADERS: tuple[str, ...] = (
    "Handoff ID",
    "Time",
    "WhatsApp Number",
    "Name",
    "Reason",
    "Captured So Far",
    "Lead ID",
    "Reply By",
    "Resolved",
)


class RepositoryUnavailable(Exception):
    """Transient failure (network, 429, 5xx) — caller retries via the outbox."""


class RepositoryContractError(Exception):
    """Headers or layout don't match the contract — not retried, needs a human."""


@runtime_checkable
class LeadRepository(Protocol):
    def check_headers(self) -> None: ...

    def append_lead(self, row: LeadRow) -> None:
        """Idempotent: does nothing if the Lead ID already exists."""

    def exists(self, lead_id: str) -> bool: ...

    def delete_lead(self, lead_id: str) -> bool: ...

    def delete_leads_created_before(self, cutoff: datetime) -> int: ...

    def append_handoff(self, row: HandoffRow) -> None: ...

    def update_handoff_reply_by(self, handoff_id: str, reply_by: str) -> None: ...

    def resolved_handoffs(self) -> list[str]: ...

    def delete_handoffs_before(self, cutoff: datetime) -> int: ...

    def sync_lists(self, lists: dict[str, list[str]]) -> None: ...
