"""InMemoryLeadRepository — behaves like the Google Sheet adapter, without the network.

Why: engine tests, evals and the `chat` CLI need a lead register that records rows exactly
as the sheet would (same layout, same idempotency and formula guard) but is free and
inspectable. Layouts come from config via RequirementSchema, like the real adapter.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from lead_capture.ports.leads import (
    RepositoryContractError,
    SheetLayout,
    SheetRow,
    column_letter,
)


class InMemoryLeadRepository:
    """LeadRepository storing each tab as a list of rows (full width, ops columns empty)."""

    def __init__(
        self,
        leads: SheetLayout,
        handoffs: SheetLayout,
        *,
        timezone: str,
        actual_headers: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        """``actual_headers`` lets tests simulate a sheet whose headers differ from config."""
        self.leads_layout = leads
        self.handoffs_layout = handoffs
        self.tz = ZoneInfo(timezone)
        self._actual = actual_headers or {leads.tab: leads.headers, handoffs.tab: handoffs.headers}
        self.leads: list[list] = []
        self.handoffs: list[list] = []
        self.lists: dict[str, list[str]] = {}

    # --- contract ---------------------------------------------------------
    def check_headers(self) -> None:
        """Compare the (simulated) sheet headers with the configured layouts."""
        for layout in (self.leads_layout, self.handoffs_layout):
            if tuple(self._actual.get(layout.tab, ())) != layout.headers:
                raise RepositoryContractError("sheet_header_mismatch")

    def append_lead(self, row: SheetRow) -> None:
        """Append unless the Lead ID exists (idempotent)."""
        if not self.exists(row.key(self.leads_layout)):
            self.leads.append(self._full(row, self.leads_layout))

    def exists(self, lead_id: str) -> bool:
        """Whether a row with this Lead ID exists."""
        return any(self._key(r, self.leads_layout) == lead_id for r in self.leads)

    def delete_lead(self, lead_id: str) -> bool:
        """Delete rows with this Lead ID."""
        before = len(self.leads)
        self.leads = [r for r in self.leads if self._key(r, self.leads_layout) != lead_id]
        return len(self.leads) < before

    def delete_leads_created_before(self, cutoff: datetime) -> int:
        """Retention: drop leads created before ``cutoff``."""
        before = len(self.leads)
        self.leads = [r for r in self.leads if not self._older(r, self.leads_layout, cutoff)]
        return before - len(self.leads)

    def append_handoff(self, row: SheetRow) -> None:
        """Append unless the Handoff ID exists (idempotent)."""
        key = row.key(self.handoffs_layout)
        if not any(self._key(r, self.handoffs_layout) == key for r in self.handoffs):
            self.handoffs.append(self._full(row, self.handoffs_layout))

    def update_handoff_reply_by(self, handoff_id: str, reply_by: str) -> None:
        """Rewrite only the reply-by cell of a handoff."""
        for r in self.handoffs:
            if self._key(r, self.handoffs_layout) == handoff_id:
                r[self.handoffs_layout.reply_by_index] = reply_by

    def resolved_handoffs(self) -> list[str]:
        """Handoff IDs whose resolved cell holds the configured resolved value."""
        layout = self.handoffs_layout
        want = (layout.resolved_value or "").strip().lower()
        return [
            self._key(r, layout)
            for r in self.handoffs
            if str(r[layout.resolved_index]).strip().lower() == want
        ]

    def delete_handoffs_before(self, cutoff: datetime) -> int:
        """Retention for handoff rows."""
        before = len(self.handoffs)
        self.handoffs = [
            r for r in self.handoffs if not self._older(r, self.handoffs_layout, cutoff)
        ]
        return before - len(self.handoffs)

    def sync_lists(self, lists: dict[str, list[str]]) -> None:
        """Keep the latest Lists-tab content."""
        self.lists = {k: list(v) for k, v in lists.items()}

    # --- helpers --------------------------------------------------------------
    def _full(self, row: SheetRow, layout: SheetLayout) -> list:
        """Guarded bot values plus empty ops columns — the width of the real tab."""
        values = row.guarded()[: layout.bot_columns]
        return values + [""] * (len(layout.headers) - len(values))

    def _key(self, row: list, layout: SheetLayout) -> str:
        """The row's ID cell (Lead ID / Handoff ID)."""
        return str(row[layout.key_index])

    def _older(self, row: list, layout: SheetLayout, cutoff: datetime) -> bool:
        """Whether the row's created cell is before ``cutoff`` (retention)."""
        created = datetime.strptime(str(row[layout.created_index]), layout.time_format)
        return created.replace(tzinfo=self.tz) < cutoff

    # --- test helpers -------------------------------------------------------
    def row(self, lead_id: str) -> list:
        """The full row for a Lead ID (tests)."""
        return next(r for r in self.leads if self._key(r, self.leads_layout) == lead_id)

    def cell(self, row: list, header: str, layout: SheetLayout | None = None):
        """A cell by header name, so tests never depend on column positions."""
        return row[(layout or self.leads_layout).index(header)]

    def ops_write(self, lead_id: str, header: str, value: str) -> None:
        """Simulate an operations edit (tests)."""
        self.row(lead_id)[self.leads_layout.index(header)] = value

    def mark_resolved(self, handoff_id: str) -> None:
        """Simulate operations resolving a handoff (tests)."""
        layout = self.handoffs_layout
        for r in self.handoffs:
            if self._key(r, layout) == handoff_id:
                r[layout.resolved_index] = layout.resolved_value

    def column(self, header: str) -> str:
        """Column letter of a Leads header (tests)."""
        return column_letter(self.leads_layout.index(header))
