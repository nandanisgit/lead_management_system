"""InMemoryLeadRepository — behaves like the Google Sheet contract, for tests and local chat."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from lead_capture.ports.leads import (
    HANDOFF_HEADERS,
    LEAD_HEADERS,
    HandoffRow,
    LeadRow,
    RepositoryContractError,
)

_OPS_COLUMNS = {"Z": 25, "AA": 26, "AB": 27, "AC": 28}


class InMemoryLeadRepository:
    def __init__(
        self,
        lead_headers: tuple[str, ...] = LEAD_HEADERS,
        handoff_headers: tuple[str, ...] = HANDOFF_HEADERS,
        timezone: str = "Asia/Kolkata",
    ) -> None:
        self.lead_headers = lead_headers
        self.handoff_headers = handoff_headers
        self.tz = ZoneInfo(timezone)
        self.leads: list[list] = []
        self.handoffs: list[list] = []
        self.lists: dict[str, list[str]] = {}

    # --- contract ---------------------------------------------------------
    def check_headers(self) -> None:
        if (
            tuple(self.lead_headers) != LEAD_HEADERS
            or tuple(self.handoff_headers) != HANDOFF_HEADERS
        ):
            raise RepositoryContractError("sheet_header_mismatch")

    def append_lead(self, row: LeadRow) -> None:
        if self.exists(row.lead_id):
            return
        self.leads.append(row.to_values() + ["", "", ""])

    def exists(self, lead_id: str) -> bool:
        return any(r[0] == lead_id for r in self.leads)

    def delete_lead(self, lead_id: str) -> bool:
        before = len(self.leads)
        self.leads = [r for r in self.leads if r[0] != lead_id]
        return len(self.leads) < before

    def delete_leads_created_before(self, cutoff: datetime) -> int:
        before = len(self.leads)
        self.leads = [r for r in self.leads if self._parse(r[1]) >= cutoff]
        return before - len(self.leads)

    def append_handoff(self, row: HandoffRow) -> None:
        if any(r[0] == row.handoff_id for r in self.handoffs):
            return
        self.handoffs.append(row.to_values() + [""])

    def update_handoff_reply_by(self, handoff_id: str, reply_by: str) -> None:
        for r in self.handoffs:
            if r[0] == handoff_id:
                r[7] = reply_by

    def resolved_handoffs(self) -> list[str]:
        return [r[0] for r in self.handoffs if str(r[8]).strip().lower() == "resolved"]

    def delete_handoffs_before(self, cutoff: datetime) -> int:
        before = len(self.handoffs)
        self.handoffs = [r for r in self.handoffs if self._parse(r[1]) >= cutoff]
        return before - len(self.handoffs)

    def sync_lists(self, lists: dict[str, list[str]]) -> None:
        self.lists = {k: list(v) for k, v in lists.items()}

    # --- test helpers -------------------------------------------------------
    def row(self, lead_id: str) -> list:
        return next(r for r in self.leads if r[0] == lead_id)

    def ops_write(self, lead_id: str, column: str, value: str) -> None:
        self.row(lead_id)[_OPS_COLUMNS[column]] = value

    def mark_resolved(self, handoff_id: str) -> None:
        for r in self.handoffs:
            if r[0] == handoff_id:
                r[8] = "Resolved"

    def _parse(self, text: str) -> datetime:
        return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=self.tz)
