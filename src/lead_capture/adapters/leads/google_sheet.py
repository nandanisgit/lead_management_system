"""GoogleSheetLeadRepository — LeadRepository over the Google Sheets REST API v4.

Why: the operations team works in a Google Sheet (intent §9). This adapter is the only code
that talks to Google. Tab names, headers, which columns the bot owns and the time format all
come from config/requirement.yaml (``sheet:``) through ``SheetLayout``; it writes only the
bot-owned columns and never the operations columns. Transient failures raise
RepositoryUnavailable so the outbox retries (contracts/lead-sheet.md).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from lead_capture.ports.leads import (
    RepositoryContractError,
    RepositoryUnavailable,
    SheetLayout,
    SheetRow,
    column_letter,
)
from lead_capture.settings import Secrets

log = logging.getLogger(__name__)
API = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def service_account_token_provider(path: str) -> Callable[[], str]:
    """Access-token callable for a service-account key file (refreshes when expired).

    Why: the service account is shared on this one sheet only (least privilege, R5).
    """
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

    def token() -> str:
        """A valid access token, refreshed when it has expired."""
        if not creds.valid:
            creds.refresh(Request())
        return creds.token

    return token


def header_difference(layout: SheetLayout, actual: list) -> str:
    """The first header cell that differs, in words, so the sheet can be fixed by hand.

    Headers come from config/requirement.yaml, not from tutees, so they are safe to show.
    """
    for i in range(max(len(actual), len(layout.headers))):
        want = layout.headers[i] if i < len(layout.headers) else None
        got = actual[i] if i < len(actual) else None
        if got != want:
            cell = f"{layout.tab}!{column_letter(i)}1"
            if want is None:
                return f"{cell} should be empty, found {got!r}"
            return f"{cell} should be {want!r}, found {got!r}"
    return f"{layout.tab} header row differs"


class GoogleSheetLeadRepository:
    """LeadRepository on a native Google Sheet."""

    def __init__(
        self,
        sheet_id: str,
        token_provider: Callable[[], str],
        *,
        leads: SheetLayout,
        handoffs: SheetLayout,
        lists_tab: str,
        timezone: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        """Build for one sheet; layouts and the Lists tab name come from the schema."""
        if not sheet_id:
            raise RepositoryContractError("LEAD_SHEET_ID not configured")
        self._base = f"{API}/{sheet_id}"
        self._token = token_provider
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._tz = ZoneInfo(timezone)
        self._leads = leads
        self._handoffs = handoffs
        self._lists_tab = lists_tab
        self._sheet_ids: dict[str, int] | None = None

    @classmethod
    def from_config(
        cls,
        secrets: Secrets,
        *,
        leads: SheetLayout,
        handoffs: SheetLayout,
        lists_tab: str,
        timezone: str,
        timeout_seconds: float,
    ) -> GoogleSheetLeadRepository:
        """Build from secrets (sheet ID, service-account file) and configured layouts."""
        if not secrets.google_service_account_file:
            raise RepositoryContractError("GOOGLE_SERVICE_ACCOUNT_FILE not configured")
        return cls(
            secrets.lead_sheet_id or "",
            service_account_token_provider(secrets.google_service_account_file),
            leads=leads,
            handoffs=handoffs,
            lists_tab=lists_tab,
            timezone=timezone,
            timeout_seconds=timeout_seconds,
        )

    # --- HTTP -----------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
        """One API call; 429/5xx/network → RepositoryUnavailable, other 4xx → contract error."""
        try:
            resp = self._client.request(
                method,
                self._base + path,
                headers={"Authorization": f"Bearer {self._token()}"},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise RepositoryUnavailable(type(exc).__name__) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise RepositoryUnavailable(f"http_{resp.status_code}")
        if resp.status_code >= 400:
            raise RepositoryContractError(f"http_{resp.status_code}")
        return resp.json() if resp.content else {}

    def _get(self, rng: str) -> list[list]:
        """Cell values of an A1 range."""
        return self._request("GET", f"/values/{quote(rng, safe='')}").get("values", [])

    def _append(self, rng: str, row: list) -> None:
        """Append one row below the table (INSERT_ROWS keeps ops edits intact)."""
        self._request(
            "POST",
            f"/values/{quote(rng, safe='')}:append",
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": [row]},
        )

    def _put(self, rng: str, rows: list[list]) -> None:
        """Overwrite an A1 range."""
        self._request(
            "PUT",
            f"/values/{quote(rng, safe='')}",
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": rows},
        )

    def _sheet_id(self, title: str) -> int:
        """Numeric tab ID (needed to delete rows); fetched once."""
        if self._sheet_ids is None:
            meta = self._request("GET", "", params={"fields": "sheets.properties(sheetId,title)"})
            self._sheet_ids = {
                s["properties"]["title"]: s["properties"]["sheetId"] for s in meta.get("sheets", [])
            }
        if title not in self._sheet_ids:
            raise RepositoryContractError(f"missing_tab_{title}")
        return self._sheet_ids[title]

    def _delete_rows(self, title: str, indexes: list[int]) -> None:
        """Delete 0-based row indexes (from the bottom up, so indexes stay valid)."""
        if not indexes:
            return
        sheet_id = self._sheet_id(title)
        requests = [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": i,
                        "endIndex": i + 1,
                    }
                }
            }
            for i in sorted(indexes, reverse=True)
        ]
        self._request("POST", ":batchUpdate", json={"requests": requests})

    def _column(self, layout: SheetLayout, index: int) -> list[str]:
        """One whole column (header included) as strings."""
        letter = column_letter(index)
        return [r[0] if r else "" for r in self._get(f"{layout.tab}!{letter}:{letter}")]

    def _rows_created_before(self, layout: SheetLayout, cutoff: datetime) -> list[int]:
        """Row indexes (excluding the header) whose created cell is before ``cutoff``."""
        out = []
        for i, value in enumerate(self._column(layout, layout.created_index)):
            if i == 0:
                continue
            try:
                created = datetime.strptime(value, layout.time_format).replace(tzinfo=self._tz)
            except ValueError:
                continue
            if created < cutoff:
                out.append(i)
        return out

    # --- contract -------------------------------------------------------------
    def check_headers(self) -> None:
        """Refuse to write if the sheet's header rows differ from the configured layouts."""
        for layout in (self._leads, self._handoffs):
            actual = (self._get(f"{layout.tab}!1:1") or [[]])[0]
            if tuple(actual) != layout.headers:
                detail = header_difference(layout, list(actual))
                log.error("sheet_header_mismatch", extra={"tab": layout.tab, "detail": detail})
                raise RepositoryContractError(f"sheet_header_mismatch: {detail}")

    def exists(self, lead_id: str) -> bool:
        """Lead ID present in the key column."""
        return lead_id in self._column(self._leads, self._leads.key_index)[1:]

    def append_lead(self, row: SheetRow) -> None:
        """Append the bot-owned columns of a lead unless its ID already exists."""
        if not self.exists(row.key(self._leads)):
            self._append(self._leads.bot_range, row.guarded()[: self._leads.bot_columns])

    def delete_lead(self, lead_id: str) -> bool:
        """Delete the row(s) with this Lead ID."""
        keys = self._column(self._leads, self._leads.key_index)
        idx = [i for i, v in enumerate(keys) if i > 0 and v == lead_id]
        self._delete_rows(self._leads.tab, idx)
        return bool(idx)

    def delete_leads_created_before(self, cutoff: datetime) -> int:
        """Retention: delete leads created before ``cutoff``."""
        idx = self._rows_created_before(self._leads, cutoff)
        self._delete_rows(self._leads.tab, idx)
        return len(idx)

    def append_handoff(self, row: SheetRow) -> None:
        """Append a handoff unless its ID already exists."""
        keys = self._column(self._handoffs, self._handoffs.key_index)[1:]
        if row.key(self._handoffs) not in keys:
            self._append(self._handoffs.bot_range, row.guarded()[: self._handoffs.bot_columns])

    def update_handoff_reply_by(self, handoff_id: str, reply_by: str) -> None:
        """Rewrite only the reply-by cell of the handoff row."""
        layout = self._handoffs
        for i, key in enumerate(self._column(layout, layout.key_index)):
            if i > 0 and key == handoff_id:
                cell = f"{layout.tab}!{column_letter(layout.reply_by_index)}{i + 1}"
                self._put(cell, [[reply_by]])
                return

    def resolved_handoffs(self) -> list[str]:
        """Handoff IDs whose resolved cell holds the configured resolved value."""
        layout = self._handoffs
        want = (layout.resolved_value or "").strip().lower()
        out = []
        for i, r in enumerate(self._get(layout.full_range)):
            resolved = len(r) > layout.resolved_index and r[layout.resolved_index]
            if i > 0 and str(resolved or "").strip().lower() == want:
                out.append(r[layout.key_index])
        return out

    def delete_handoffs_before(self, cutoff: datetime) -> int:
        """Retention for handoff rows."""
        idx = self._rows_created_before(self._handoffs, cutoff)
        self._delete_rows(self._handoffs.tab, idx)
        return len(idx)

    def sync_lists(self, lists: dict[str, list[str]]) -> None:
        """Clear and rewrite the Lists tab: one column per list, header in row 1."""
        headers = list(lists)
        depth = max((len(v) for v in lists.values()), default=0)
        rows = [headers] + [
            [lists[h][i] if i < len(lists[h]) else "" for h in headers] for i in range(depth)
        ]
        self._request("POST", f"/values/{quote(self._lists_tab + '!A:ZZ', safe='')}:clear")
        self._put(f"{self._lists_tab}!A1", rows)
