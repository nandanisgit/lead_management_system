"""LeadRepository port — where confirmed leads and handoffs are recorded for operations.

Why: the Google Sheet is only the v1 lead register; a database or CRM will replace it
(research R14). Code talks to this interface, and the column layout comes from
config/requirement.yaml (``sheet:``) as a ``SheetLayout`` instead of being hard-coded, so
adding a field or column never touches the adapters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def guard(value: Any) -> Any:
    """Store text starting with = + - @ literally, so the sheet never runs it as a formula.

    Why: tutee-supplied text reaches the sheet; a value like "=HYPERLINK(...)" must not be
    executed (formula injection). Numbers are left as numbers.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def column_letter(index: int) -> str:
    """0-based column index → sheet column letters (0 → A, 25 → Z, 26 → AA)."""
    letters = ""
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


class SheetLayout(BaseModel):
    """Column layout of one tab, generated from config (see RequirementSchema.leads_layout).

    The first ``bot_columns`` columns are written by the bot; the rest belong to operations
    and are never written.
    """

    tab: str
    headers: tuple[str, ...]
    bot_columns: int
    key_index: int
    created_index: int
    time_format: str
    reply_by_index: int | None = None
    resolved_index: int | None = None
    resolved_value: str | None = None

    def index(self, header: str) -> int:
        """Position of a column by its header (so callers never use magic indexes)."""
        return self.headers.index(header)

    @property
    def bot_range(self) -> str:
        """A1 range covering only the bot-owned columns, e.g. "Leads!A:Z"."""
        return f"{self.tab}!A:{column_letter(self.bot_columns - 1)}"

    @property
    def full_range(self) -> str:
        """A1 range covering every column of the tab."""
        return f"{self.tab}!A:{column_letter(len(self.headers) - 1)}"


class SheetRow(BaseModel):
    """Values for the bot-owned columns of one row, in layout order."""

    values: list[Any]

    def key(self, layout: SheetLayout) -> str:
        """The row's identifier (Lead ID / Handoff ID) — used for idempotent writes."""
        return str(self.values[layout.key_index])

    def guarded(self) -> list[Any]:
        """Values made safe for the sheet (see ``guard``)."""
        return [guard(v) for v in self.values]


class RepositoryUnavailable(Exception):
    """Transient failure (network, 429, 5xx) — the caller retries via the outbox."""


class RepositoryContractError(Exception):
    """Headers or layout don't match the config — not retried, needs a human."""


@runtime_checkable
class LeadRepository(Protocol):
    """Everything the service needs from the lead register (contracts/lead-sheet.md)."""

    def check_headers(self) -> None:
        """Raise RepositoryContractError unless the tabs' headers match the config."""

    def append_lead(self, row: SheetRow) -> None:
        """Record a confirmed lead. Idempotent: does nothing if the Lead ID already exists."""

    def exists(self, lead_id: str) -> bool:
        """Whether a lead with this ID is recorded."""

    def delete_lead(self, lead_id: str) -> bool:
        """Delete a lead (deletion request, FR-025). Returns whether one was deleted."""

    def delete_leads_created_before(self, cutoff: datetime) -> int:
        """Retention (FR-026): delete leads created before ``cutoff``; returns how many."""

    def append_handoff(self, row: SheetRow) -> None:
        """Record a handoff so operations see it (FR-024). Idempotent on Handoff ID."""

    def update_handoff_reply_by(self, handoff_id: str, reply_by: str) -> None:
        """Move a handoff's reply-by time when the tutee writes again."""

    def resolved_handoffs(self) -> list[str]:
        """Handoff IDs operations have marked as resolved."""

    def delete_handoffs_before(self, cutoff: datetime) -> int:
        """Retention for handoff rows; returns how many were deleted."""

    def sync_lists(self, lists: dict[str, list[str]]) -> None:
        """Rewrite the Lists tab (dropdown values) from config."""
