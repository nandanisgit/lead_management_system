"""GoogleSheetLeadRepository — LeadRepository over the Google Sheets REST API v4.

Contract: specs/001-whatsapp-lead-capture/contracts/lead-sheet.md. Appends columns A–Z only;
never writes AA–AC. Transient failures raise RepositoryUnavailable (the outbox retries).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from lead_capture.ports.leads import (
    HANDOFF_HEADERS,
    LEAD_HEADERS,
    HandoffRow,
    LeadRow,
    RepositoryContractError,
    RepositoryUnavailable,
)
from lead_capture.settings import Secrets

log = logging.getLogger(__name__)
API = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LEADS, HANDOFFS, LISTS = "Leads", "Handoffs", "Lists"
TIME_FMT = "%Y-%m-%d %H:%M"


def service_account_token_provider(path: str) -> Callable[[], str]:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

    def token() -> str:
        if not creds.valid:
            creds.refresh(Request())
        return creds.token

    return token


class GoogleSheetLeadRepository:
    def __init__(
        self,
        sheet_id: str,
        token_provider: Callable[[], str],
        *,
        timezone: str = "Asia/Kolkata",
        client: httpx.Client | None = None,
    ) -> None:
        if not sheet_id:
            raise RepositoryContractError("LEAD_SHEET_ID not configured")
        self._base = f"{API}/{sheet_id}"
        self._token = token_provider
        self._client = client or httpx.Client(timeout=15)
        self._tz = ZoneInfo(timezone)
        self._sheet_ids: dict[str, int] | None = None

    @classmethod
    def from_secrets(cls, secrets: Secrets, timezone: str) -> GoogleSheetLeadRepository:
        if not secrets.google_service_account_file:
            raise RepositoryContractError("GOOGLE_SERVICE_ACCOUNT_FILE not configured")
        return cls(
            secrets.lead_sheet_id or "",
            service_account_token_provider(secrets.google_service_account_file),
            timezone=timezone,
        )

    # --- HTTP -----------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
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
        return self._request("GET", f"/values/{quote(rng, safe='')}").get("values", [])

    def _append(self, rng: str, row: list) -> None:
        self._request(
            "POST",
            f"/values/{quote(rng, safe='')}:append",
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": [row]},
        )

    def _put(self, rng: str, rows: list[list]) -> None:
        self._request(
            "PUT",
            f"/values/{quote(rng, safe='')}",
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": rows},
        )

    def _sheet_id(self, title: str) -> int:
        if self._sheet_ids is None:
            meta = self._request("GET", "", params={"fields": "sheets.properties(sheetId,title)"})
            self._sheet_ids = {
                s["properties"]["title"]: s["properties"]["sheetId"] for s in meta.get("sheets", [])
            }
        if title not in self._sheet_ids:
            raise RepositoryContractError(f"missing_tab_{title}")
        return self._sheet_ids[title]

    def _delete_rows(self, title: str, indexes: list[int]) -> None:
        """Delete 0-based row indexes (descending so indexes stay valid)."""
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

    def _parse(self, text: str) -> datetime | None:
        try:
            return datetime.strptime(str(text), TIME_FMT).replace(tzinfo=self._tz)
        except ValueError:
            return None

    # --- contract -------------------------------------------------------------
    def check_headers(self) -> None:
        leads = (self._get(f"{LEADS}!1:1") or [[]])[0]
        handoffs = (self._get(f"{HANDOFFS}!1:1") or [[]])[0]
        if tuple(leads) != LEAD_HEADERS or tuple(handoffs) != HANDOFF_HEADERS:
            log.error("sheet_header_mismatch")
            raise RepositoryContractError("sheet_header_mismatch")

    def _lead_ids(self) -> list[str]:
        return [r[0] if r else "" for r in self._get(f"{LEADS}!A:A")]

    def exists(self, lead_id: str) -> bool:
        return lead_id in self._lead_ids()[1:]

    def append_lead(self, row: LeadRow) -> None:
        if self.exists(row.lead_id):
            return
        self._append(f"{LEADS}!A:Z", row.to_values())

    def delete_lead(self, lead_id: str) -> bool:
        ids = self._lead_ids()
        idx = [i for i, v in enumerate(ids) if i > 0 and v == lead_id]
        self._delete_rows(LEADS, idx)
        return bool(idx)

    def delete_leads_created_before(self, cutoff: datetime) -> int:
        rows = self._get(f"{LEADS}!A:B")
        idx = []
        for i, r in enumerate(rows):
            if i == 0 or len(r) < 2:
                continue
            created = self._parse(r[1])
            if created and created < cutoff:
                idx.append(i)
        self._delete_rows(LEADS, idx)
        return len(idx)

    def append_handoff(self, row: HandoffRow) -> None:
        ids = [r[0] for r in self._get(f"{HANDOFFS}!A:A")[1:] if r]
        if row.handoff_id in ids:
            return
        self._append(f"{HANDOFFS}!A:H", row.to_values())

    def update_handoff_reply_by(self, handoff_id: str, reply_by: str) -> None:
        for i, r in enumerate(self._get(f"{HANDOFFS}!A:A")):
            if i > 0 and r and r[0] == handoff_id:
                self._put(f"{HANDOFFS}!H{i + 1}", [[reply_by]])
                return

    def resolved_handoffs(self) -> list[str]:
        out = []
        for i, r in enumerate(self._get(f"{HANDOFFS}!A:I")):
            if i > 0 and len(r) >= 9 and str(r[8]).strip().lower() == "resolved":
                out.append(r[0])
        return out

    def delete_handoffs_before(self, cutoff: datetime) -> int:
        idx = []
        for i, r in enumerate(self._get(f"{HANDOFFS}!A:B")):
            if i == 0 or len(r) < 2:
                continue
            at = self._parse(r[1])
            if at and at < cutoff:
                idx.append(i)
        self._delete_rows(HANDOFFS, idx)
        return len(idx)

    def sync_lists(self, lists: dict[str, list[str]]) -> None:
        headers = list(lists)
        depth = max((len(v) for v in lists.values()), default=0)
        rows = [headers] + [
            [lists[h][i] if i < len(lists[h]) else "" for h in headers] for i in range(depth)
        ]
        self._request("POST", f"/values/{quote(LISTS + '!A:Z', safe='')}:clear")
        self._put(f"{LISTS}!A1", rows)


def column_index(letter: str) -> int:
    """'A' -> 0, 'AA' -> 26."""
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - 64)
    return n - 1
