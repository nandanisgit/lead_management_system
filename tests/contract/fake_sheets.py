"""A tiny in-memory Google Sheets REST backend for respx (enough for GoogleSheetLeadRepository)."""

from __future__ import annotations

import json
import re
from urllib.parse import unquote

import httpx

from lead_capture.adapters.leads.google_sheet import column_index
from lead_capture.ports.leads import HANDOFF_HEADERS, LEAD_HEADERS

SHEET_ID = "SHEET"
BASE = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"


class FakeSheets:
    def __init__(self, lead_headers=LEAD_HEADERS):
        self.grids = {
            "Leads": [list(lead_headers)],
            "Handoffs": [list(HANDOFF_HEADERS)],
            "Lists": [],
        }
        self.ids = {"Leads": 0, "Handoffs": 1, "Lists": 2}
        self.fail_next: int | None = None
        self.writes: list[tuple[str, str]] = []  # (method, range) for write calls

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
        lo, hi = column_index(m.group(1)), column_index(m.group(2))
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
            self.grids[title].extend(json.loads(request.content)["values"])
            return httpx.Response(200, json={})
        if rng.endswith(":clear"):
            title, _ = self._split(rng.removesuffix(":clear"))
            self.grids[title] = []
            return httpx.Response(200, json={})
        if request.method == "PUT":
            self.writes.append(("put", rng))
            title, a1 = self._split(rng)
            m = re.fullmatch(r"([A-Z]+)(\d+)", a1)
            col, row0 = column_index(m.group(1)), int(m.group(2)) - 1
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

    # helpers for the suite ---------------------------------------------------------
    def row(self, title, key):
        return next(r for r in self.grids[title][1:] if r and r[0] == key)

    def set_cell(self, title, key, col_letter, value):
        r = self.row(title, key)
        i = column_index(col_letter)
        while len(r) <= i:
            r.append("")
        r[i] = value
