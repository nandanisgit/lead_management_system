# Data Model: WhatsApp Lead Capture

**Feature**: [spec.md](spec.md) · **Research**: [research.md](research.md)

Two stores:

- **Bot working store** (SQLite) — contacts, conversations, messages, lead outbox.
- **Operational lead register** (Google Sheet) — `Leads`, `Handoffs` and `Lists`
  tabs; column contract in [contracts/lead-sheet.md](contracts/lead-sheet.md).

All timestamps are stored in UTC and shown in IST (Asia/Kolkata).

## Entities (bot working store)

### Contact
One WhatsApp user.

| Field | Type | Rules |
|---|---|---|
| `id` | integer PK | |
| `wa_number` | text, unique | channel address: E.164 `+91…` on WhatsApp, `tg:<chat id>` on Telegram (FR-031) |
| `wa_profile_name` | text, nullable | from webhook |
| `contact_name` | text, nullable | as the tutee gives it |
| `relationship` | enum, nullable | `parent` / `student` / `other` |
| `language` | enum | `en` / `hi`; latest detected |
| `consent_at` | timestamp, nullable | set when consent given (FR-005) |
| `rate_limited_until` | timestamp, nullable | set when a turn limit is hit (FR-030); turns are ignored until then. Turn counts are computed from inbound `Message` rows in the last hour / day |
| `created_at`, `updated_at` | timestamp | |

### Conversation
One requirement being gathered for one student.

| Field | Type | Rules |
|---|---|---|
| `id` | integer PK | |
| `contact_id` | FK → Contact | |
| `state` | enum | see lifecycle below |
| `collected` | JSON | validated values only — shape = `Requirement` below |
| `student_key` | text, nullable | normalised student name; with `contact_id` identifies the student |
| `close_reason` | enum, nullable | `declined_consent` / `not_interested` / `out_of_area` / `opted_out` / `deletion_request` |
| `handoff_reason` | enum, nullable | `requested` / `not_understood` / `complaint` / `sensitive` |
| `handoff_at` | timestamp, nullable | |
| `misunderstand_streak` | integer | resets on a successful turn; reaching `conversation.misunderstand_handoff_threshold` (default 3) → handoff (FR-023) |
| `consent_by_minor` | boolean | true when `minor_alone` is set after consent was given by the student (FR-029); shown in the lead's Notes |
| `minor_alone` | boolean | true when FR-029 applies: `relationship = student` and `grade_level` in `lists.minor_grade_levels`, or the model's `likely_minor_alone` signal |
| `source` | text | campaign ID from referral data, else `organic` |
| `lead_id` | text, nullable | set on confirmation |
| `first_inbound_at`, `last_inbound_at`, `last_outbound_at` | timestamp | 24-hour window uses `last_inbound_at` |
| `created_at`, `updated_at` | timestamp | |

Constraint: at most one conversation per (`contact_id`, `student_key`) in state
`in_progress`, `confirming`, `stalled` or `handed_over`; and at most one
`completed` conversation per (`contact_id`, `student_key`) whose lead is still
active (FR-021).

### Message
Transcript entry. Deleted after 90 days (FR-026).

| Field | Type | Rules |
|---|---|---|
| `id` | integer PK | |
| `conversation_id` | FK → Conversation, nullable | null before a conversation exists |
| `contact_id` | FK → Contact | |
| `wa_message_id` | text, unique | deduplication key (FR-017) |
| `direction` | enum | `in` / `out` / `echo` (sent by a human from the Business app) |
| `type` | enum | `text` / `interactive` / `unsupported` |
| `body` | text | never written to logs (FR-027) |
| `created_at` | timestamp | |

### LeadOutbox
Confirmed leads waiting to be (or already) written to the sheet.

| Field | Type | Rules |
|---|---|---|
| `lead_id` | text PK | `L-YYYYMMDD-XXXX`, `XXXX` = 4 random base32 chars |
| `conversation_id` | FK → Conversation | |
| `row` | JSON | exact values for sheet columns A–Z |
| `status` | enum | `pending` / `synced` / `deleted` |
| `attempts` | integer | |
| `last_error` | text, nullable | error class only, no personal data |
| `created_at`, `synced_at` | timestamp | |

### UsageEvent
Cost tracking (research R15). IDs and counts only — no personal data.

| Field | Type | Rules |
|---|---|---|
| `id` | integer PK | |
| `conversation_id` | FK → Conversation, nullable | |
| `kind` | enum | `extract` / `reply` / `message_out` |
| `model` | text, nullable | model name for `extract` / `reply` |
| `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` | integer | from `TokenUsage` |
| `created_at` | timestamp | deleted after `retention.usage_days` (default 90) |

## Value object: Requirement

The validated requirement stored in `Conversation.collected` and copied into a
lead. **Defined only in `config/requirement.yaml`** (constitution Principle VII): the
table below documents the v1 configuration; `Requirement.apply` enforces whatever the
config says, and adding a field needs no code change (docs/coding-guidelines.md §1).
Stored in `Conversation.collected` as `{"values": {...}, "out_of_area": bool}`.

| Field | Required | Validation |
|---|---|---|
| `contact_name` | yes | 1–60 chars |
| `phone` | yes | phone number, normalised to `+<country><number>` (default country 91); pre-filled from WhatsApp, asked on Telegram (FR-032) |
| `relationship` | yes | `parent` / `student` / `other` |
| `student_name` | yes | 1–60 chars; defaults to `contact_name` when `relationship = student` |
| `grade_level` | yes | one of `lists.grade_levels` (e.g. `Class 1`…`Class 12`, `Undergraduate`, `Postgraduate`, `Adult`) |
| `board` | if grade is a school class | one of `CBSE`, `ICSE`, `State`, `IB`, `IGCSE`; `University` / `N/A` otherwise |
| `subjects` | yes | 1–5 items from `lists.subjects` (unknown subject → ask to clarify) |
| `mode` | yes | `online` / `home` / `either` |
| `area` | if mode ≠ `online` | 2–80 chars |
| `city` | if mode ≠ `online` | one of the six NCR cities; otherwise triggers the out-of-area flow (FR-012) |
| `pincode` | optional | 6 digits; if given, must fall in NCR PIN ranges when mode ≠ `online` |
| `schedule` | yes | days + time window, normalised text, 3–120 chars |
| `start_date` | yes | `ASAP` or a date from today to +180 days |
| `budget_min`, `budget_max` | yes | positive integers in ₹; `min ≤ max`; a single figure sets both |
| `budget_unit` | yes | `per_hour` / `per_month` |
| `goal` | optional | one of `lists.goals` or free text ≤ 120 chars |
| `sessions_per_week` | optional | 1–7 |
| `tutor_preferences` | optional | ≤ 200 chars |
| `level_notes` | optional | ≤ 300 chars |
| `email` | optional | valid email |
| `guardian_name` | if `minor_alone` | 1–60 chars (FR-029) |
| `guardian_relationship` | if `minor_alone` | `mother` / `father` / `guardian` / `other` |

**Missing-field order** (`ask_groups:` in config; what the bot asks next, grouped naturally):
consent → contact_name & relationship → student_name → grade_level & board →
subjects → mode → area & city → schedule → start_date → budget → guardian_name &
guardian_relationship (only if `minor_alone`) → (optional fields if the
conversation allows) → summary.

`mode = either` outside NCR is stored as `online` (spec edge case).

## Conversation lifecycle

```text
                ┌──────────── consent declined ─────────────┐
                │                                           ▼
(new) ──► awaiting_consent ──consent──► in_progress ──all required──► confirming
                                          ▲   │                         │  │
                       tutee returns ─────┘   │ 24 h silent             │  │ correction
                             stalled ◄────────┘                         │  └──► in_progress
                                                                        │ confirm
                                                                        ▼
                                                                    completed (lead in outbox)

any active state ──handoff──► handed_over ──resolved / 72 h──► in_progress (or completed/closed)
any active state ──not interested / out of area declined / STOP──► closed (close_reason)
```

- `completed` and `closed` are terminal for that conversation; a new need for
  the same or another student starts a new conversation.
- Only the transition `confirming → completed` creates a `LeadOutbox` row.

## Sheet-side entities

| Tab | One row per | Writer | Contract |
|---|---|---|---|
| `Leads` | confirmed lead | bot appends A–Z; ops owns Z updates and AA–AC | [lead-sheet.md](contracts/lead-sheet.md) |
| `Handoffs` | handoff event | bot appends A–H and updates H (reply-by time); ops sets I (`Resolved`) | [lead-sheet.md](contracts/lead-sheet.md) |
| `Lists` | allowed value | CLI `sync-lists` from `config/requirement.yaml` (`sheet.lists_tab`) | [lead-sheet.md](contracts/lead-sheet.md) |

## Retention

| Data | Kept for | Removed by |
|---|---|---|
| `Message` rows | 90 days from `created_at` | daily job |
| `UsageEvent` rows | `retention.usage_days` (default 90) | daily job |
| `Conversation`, `LeadOutbox`, sheet `Leads` row | 1 year from creation | daily job (sheet row matched by Lead ID) |
| `Handoffs` rows | 90 days | daily job |
| `Contact` | until it has no conversations left | daily job |
| Everything for a contact | immediately on a deletion request (FR-025) | request handler |
