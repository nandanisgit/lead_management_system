"""A tiny in-memory Google Sheets REST backend for respx (enough for GoogleSheetLeadRepository)."""

from __future__ import annotations

import json
import re
from urllib.parse import unquote

import httpx

from tests.contract.lead_repository_suite import HANDOFFS, LEADS

SHEET_ID = "SHEET"
BASE = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"


def col_index(letters: str) -> int:
    """'A' → 0, 'AA' → 26."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


class FakeSheets:
    """Holds tab grids and answers the handful of API calls the adapter makes."""

    def __init__(self, lead_headers=None):
        self.grids = {
            LEADS.tab: [list(lead_headers or LEADS.headers)],
            HANDOFFS.tab: [list(HANDOFFS.headers)],
            "Lists": [],
        }
        self.ids = {LEADS.tab: 0, HANDOFFS.tab: 1, "Lists": 2}
        self.fail_next: int | None = None
        self.writes: list[tuple[str, str]] = []

    def _split(self, rng):
        title, _, a1 = rng.partition("!")
        return title, a1

    def _read(self, rng):
        title, a1 = self._split(rng)
        grid = self.grids[title]
        m = re.fullmatch(r"(\d+):(\d+)", a1)
        if m:
            return [list(r) for r in grid[int(m.group(1)) - 1 : int(m.group(2))]]
        m = re.fullmatch(r"([A-Z]+):([A-Z]+)", a1)
        lo, hi = col_index(m.group(1)), col_index(m.group(2))
        out = [list(r[lo : hi + 1]) for r in grid]
        while out and not any(out[-1]):
            out.pop()
        return out

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail_next:
            code, self.fail_next = self.fail_next, None
            return httpx.Response(code)
        path = unquote(request.url.path.split(SHEET_ID, 1)[1])
        if path == "":
            sheets = [{"properties": {"sheetId": i, "title": t}} for t, i in self.ids.items()]
            return httpx.Response(200, json={"sheets": sheets})
        if path == ":batchUpdate":
            for req in json.loads(request.content)["requests"]:
                r = req["deleteDimension"]["range"]
                title = next(t for t, i in self.ids.items() if i == r["sheetId"])
                del self.grids[title][r["startIndex"] : r["endIndex"]]
            return httpx.Response(200, json={})
        rng = path.removeprefix("/values/")
        if rng.endswith(":append"):
            rng = rng.removesuffix(":append")
            self.writes.append(("append", rng))
            title, _ = self._split(rng)
            for row in json.loads(request.content)["values"]:
                self.grids[title].append(row + [""] * (len(self.grids[title][0]) - len(row)))
            return httpx.Response(200, json={})
        if rng.endswith(":clear"):
            title, _ = self._split(rng.removesuffix(":clear"))
            self.grids[title] = []
            return httpx.Response(200, json={})
        if request.method == "PUT":
            self.writes.append(("put", rng))
            title, a1 = self._split(rng)
            m = re.fullmatch(r"([A-Z]+)(\d+)", a1)
            col, row0 = col_index(m.group(1)), int(m.group(2)) - 1
            grid = self.grids[title]
            for dr, values in enumerate(json.loads(request.content)["values"]):
                while len(grid) <= row0 + dr:
                    grid.append([])
                r = grid[row0 + dr]
                while len(r) < col + len(values):
                    r.append("")
                r[col : col + len(values)] = values
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"values": self._read(rng)})

    def row(self, title, key, key_index=0):
        return next(r for r in self.grids[title][1:] if r and r[key_index] == key)

    def set_cell(self, title, key, index, value):
        self.row(title, key)[index] = value
