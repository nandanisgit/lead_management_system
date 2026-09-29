# Contract: Operational Lead Register (Google Sheet)

A native Google Sheet on a shared Drive. The service account has **editor
access to this one file only**. Sheet ID comes from `LEAD_SHEET_ID`.

Header rows are frozen and must not be renamed or reordered. The service checks
the header row on start-up and refuses to write if it doesn't match this
contract (logs `sheet_header_mismatch`).

## Tab `Leads`

Columns A–Y are written once by the bot when a lead is appended. Column Z is
written as `NEW` by the bot and owned by the operations team afterwards.
Columns AA–AC are never written by the bot.

| Col | Header | Value written by bot |
|---|---|---|
| A | Lead ID | `L-YYYYMMDD-XXXX` |
| B | Created At | `YYYY-MM-DD HH:MM` IST |
| C | WhatsApp Number | `+91XXXXXXXXXX` (text, prefixed with `'` so Sheets keeps the `+`) |
| D | Contact Name | |
| E | Relationship | `parent` / `student` / `other` |
| F | Student Name | |
| G | Class / Level | from `Lists` |
| H | Board | from `Lists` |
| I | Subjects | comma-separated |
| J | Mode | `online` / `home` / `either` |
| K | Area | blank if online |
| L | City | blank if online |
| M | PIN Code | blank if not given |
| N | Preferred Schedule | |
| O | Start Date | `ASAP` or `YYYY-MM-DD` |
| P | Budget Min (₹) | integer |
| Q | Budget Max (₹) | integer |
| R | Budget Unit | `per hour` / `per month` |
| S | Goal | optional |
| T | Sessions per Week | optional |
| U | Tutor Preferences | optional |
| V | Notes | level notes and optional email; for FR-029 leads starts with `MINOR – contact parent/guardian: <name> (<relationship>)` |
| W | Language | `English` / `Hindi` |
| X | Source | campaign ID or `organic` |
| Y | Consent At | `YYYY-MM-DD HH:MM` IST |
| Z | Status | `NEW` |
| AA | Assigned To | — (ops) |
| AB | Ops Notes | — (ops) |
| AC | Last Updated | — (ops) |

**Write rules**
- Append only (`values.append`, range `Leads!A:Z`, `INSERT_ROWS`, `USER_ENTERED`).
- Before appending, look up column A for the Lead ID; if present, mark the outbox row `synced` without writing.
- Deleting a row (retention or deletion request) finds it by Lead ID and deletes the whole row.
- Text values starting with `=`, `+`, `-` or `@` are prefixed with `'` (formula-injection guard).

## Tab `Handoffs`

| Col | Header | Writer |
|---|---|---|
| A | Handoff ID | bot (`H-YYYYMMDD-XXXX`) |
| B | Time | bot (IST) |
| C | WhatsApp Number | bot |
| D | Name | bot |
| E | Reason | bot (`requested` / `not understood` / `complaint` / `sensitive`) |
| F | Captured So Far | bot (short summary of validated fields) |
| G | Lead ID | bot (if a lead exists) |
| H | Resolved | ops (`Resolved` when done) |

## Tab `Lists`

One column per list (Class / Level, Board, Subjects, City, Mode, Budget Unit,
Status). Written by the `sync-lists` command from `config/lists.yaml`; used as
data-validation ranges for dropdowns in `Leads`.

## `LeadRepository` interface

All code reaches the sheet only through this interface (constitution
Principle II). Implementations: `GoogleSheetLeadRepository`,
`InMemoryLeadRepository` (tests).

| Method | Behaviour |
|---|---|
| `append_lead(row: LeadRow) -> None` | idempotent append of columns A–Z |
| `exists(lead_id: str) -> bool` | Lead ID present in column A |
| `delete_lead(lead_id: str) -> bool` | delete the row if present |
| `delete_leads_created_before(cutoff: datetime) -> int` | retention |
| `append_handoff(row: HandoffRow) -> None` | append to `Handoffs` |
| `resolved_handoffs() -> list[str]` | Handoff IDs marked `Resolved` |
| `delete_handoffs_before(cutoff: datetime) -> int` | retention |
| `sync_lists(lists: AllowedLists) -> None` | rewrite the `Lists` tab |
| `check_headers() -> None` | raise if headers don't match this contract |

Errors: transient Google errors raise `RepositoryUnavailable` (caller retries
via the outbox); contract errors raise `RepositoryContractError` (not retried,
alert).
