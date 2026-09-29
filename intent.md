# Intent: WhatsApp Tutor-Lead Capture

**Status:** Draft · **Stage:** 0 — Intent · **Last updated:** 2026-09-29

> This file records **why** this system exists and **what "done" means**.
> It is the source of truth for humans and AI coding agents. When a task conflicts
> with this file, stop and ask instead of guessing.

---

## 1. Problem

Tutees (students, or parents on their behalf) reach out on WhatsApp asking for a
tutor. Today these chats are handled manually: questions are asked inconsistently,
key details get missed, follow-ups are slow, and the information lives only inside
chat threads. The operations team then has to re-ask questions before it can
search for a suitable tutor.

## 2. Intent (one sentence)

Have a **natural, human-like WhatsApp conversation** with every tutee that
**collects everything needed to find them a tutor**, and then **save a complete,
structured lead into the operational database** for the team to process.

## 3. Actors

| Actor | Role |
|---|---|
| **Tutee** | Student or parent/guardian looking for a tutor; chats on WhatsApp |
| **Lead Assistant (bot)** | Converses with the tutee, extracts and validates requirements |
| **Operations team** | Picks up completed leads from the Google Sheet and searches for tutors |
| **Human agent** | Takes over the chat when the bot can't help or the tutee asks for a person |

## 4. Goals (in scope)

- **G1 — Human-like conversation.** Warm, short, conversational messages; one or two questions at a time; understands free-text, Hinglish and typos; never feels like a form.
- **G2 — Complete requirement capture.** Collect every *required* field in §6 before a lead is marked complete; ask naturally for anything missing.
- **G3 — Smart extraction.** If the tutee gives several details in one message ("Class 9 CBSE maths and science, home tuition in HSR Layout, evenings"), capture all of them and don't ask again.
- **G4 — Confirmation.** Before saving, play back a short summary and let the tutee confirm or correct it.
- **G5 — Persist the lead.** Append the confirmed lead as a new row in the operational Google Sheet with status `NEW`, ready for processing.
- **G6 — Resume and deduplicate.** If the tutee drops off and returns, continue from where they left off; one active lead per phone number + student.
- **G7 — Human handoff.** Hand over to a human agent on request, on repeated confusion, or on complaints/sensitive topics.

## 5. Non-goals (out of scope for v1)

- Searching, matching or recommending tutors
- Pricing quotes, payments, invoices or bookings
- Scheduling demo classes
- Tutor onboarding over WhatsApp
- Channels other than WhatsApp (web chat, SMS, calls)
- Marketing broadcasts

## 6. Information to capture

### Required (lead is incomplete without these)

| Field | Example | Notes |
|---|---|---|
| `contact_name` | "Priya" | Person chatting |
| `relationship` | parent / student / other | Who is chatting |
| `student_name` | "Aarav" | May equal `contact_name` |
| `grade_level` | Class 9, Class 12, BTech 2nd yr, Adult | Normalise to a standard list |
| `board_or_curriculum` | CBSE, ICSE, State, IB, IGCSE, University, N/A | Ask only if school-level |
| `subjects` | [Maths, Science] | One or more |
| `mode` | online / home / either | |
| `location` | Area + city, or PIN code | Required only if mode is home or either. Home tuition is serviceable **only in Delhi/NCR** (Delhi, Noida, Greater Noida, Gurugram, Ghaziabad, Faridabad) — see §7 |
| `preferred_schedule` | Weekday evenings, 6–8 pm | Days + time window |
| `start_date` | ASAP / specific date | |
| `budget_range` | ₹500–700 per hour, or ₹6,000 per month | Accept per-hour or per-month; store unit alongside the amount |

### Optional (ask if the conversation allows, never block on them)

| Field | Example |
|---|---|
| `goal` | Board exam prep, concept clarity, homework help, competitive exam (JEE/NEET) |
| `sessions_per_week` | 3 |
| `tutor_preferences` | Gender, language, experience |
| `current_level_notes` | "Weak in algebra, scored 55% in last test" |
| `email` | Alternate contact |

### Captured automatically (never asked)

`whatsapp_number`, `wa_profile_name`, first/last message timestamps, source
(e.g. ad click-to-WhatsApp campaign ID), full conversation transcript reference.

## 7. Conversation design

**Tone:** friendly, polite, concise, like a helpful coordinator. Use their name.
Minimal emojis.

**Languages:** English and Hindi only (including Hinglish and Hindi typed in
Roman script). Reply in the language the tutee uses. If they write in another
language, reply politely in English and Hindi that only these two are supported.

**Serviceable area:** home tuition is offered only in Delhi/NCR. If a tutee
wants home tuition elsewhere, say so kindly and offer online classes instead;
if they decline, close the lead as `CLOSED` with reason `out_of_area`.

**Budget:** ask naturally ("Do you have a budget in mind, per hour or per
month?"). **Never suggest or share typical budget ranges or rates.** If the
tutee is unsure, ask for an approximate figure they'd be comfortable with — the
lead cannot be completed without a budget.

**Flow (flexible, not a fixed script):**

1. **Greet & consent** — introduce as the tutoring team's assistant, mention that details will be stored to find a tutor, get a go-ahead.
2. **Understand the need** — open question: "Tell me a bit about what you're looking for."
3. **Fill gaps** — ask only for missing required fields, grouped naturally (e.g. class + board together).
4. **Clarify** — resolve ambiguity ("Is that ICSE or CBSE?"; "Which area in Delhi?").
5. **Summarise & confirm** — short bullet summary; tutee confirms or edits.
6. **Close** — thank them and say what happens next. The operations team works **every day, 10 AM – 5 PM IST** (including weekends and holidays):
   - Confirmed between 10 AM and 5 PM → "Our team will get in touch with you today."
   - Confirmed before 10 AM → "Our team will reach out after 10 AM today."
   - Confirmed after 5 PM → "Our team will reach out after 10 AM tomorrow."

**Rules:**
- Max 2 questions per message; keep messages under ~60 words.
- Never re-ask for something already given.
- Use WhatsApp interactive buttons/lists for closed choices (mode, board) but always accept typed answers.
- If a message is off-topic, answer briefly if safe and steer back.
- Offer "talk to a person" at any time.

**Sample exchange:**

> **Tutee:** Hi, need a maths tutor for my son
> **Bot:** Hi! Happy to help find a maths tutor for your son 😊 Which class is he in, and which board — CBSE, ICSE or State?
> **Tutee:** class 8 cbse. also science if possible
> **Bot:** Got it — Class 8 CBSE, Maths and Science. Would you prefer online classes or a tutor coming home?
> **Tutee:** home, we're in Dwarka sector 12
> **Bot:** Great, Dwarka Sector 12 noted. Which days and times usually work best for him?
> **Tutee:** shaam ko 5 ke baad, weekdays
> **Bot:** Theek hai — weekdays, 5 baje ke baad. Aapka budget kitna hai, per hour ya per month?

## 8. Lead lifecycle

```
IN_PROGRESS ──(all required fields + confirmed)──▶ NEW ──▶ (ops processing, out of scope)
     │
     ├──(no reply 24h)──▶ STALLED ──(tutee returns)──▶ IN_PROGRESS
     ├──(handoff)──────▶ HUMAN_HANDLING
     └──(opt-out / not interested / out_of_area)──▶ CLOSED (with close_reason)
```

Only `NEW` leads are written to the operations Google Sheet; from there the
operations team moves them through their own statuses (§9.1, column Z).

## 9. Data model

### 9.1 Operational DB — Google Sheet on Google Drive (v1)

For now the operational DB is a **native Google Sheet** (not an uploaded .xlsx) in a shared Google Drive folder.
The operations team works directly in it. The bot writes **only confirmed leads
(status `NEW`)** to it; in-progress chats never appear there.

**Tab `Leads`** — one row per student requirement. Columns in this fixed order
(header row is frozen; do not rename or reorder):

| Col | Header | Written by | Format |
|---|---|---|---|
| A | Lead ID | Bot | `L-YYYYMMDD-XXXX` (unique) |
| B | Created At | Bot | `YYYY-MM-DD HH:MM` IST |
| C | WhatsApp Number | Bot | `+91XXXXXXXXXX` |
| D | Contact Name | Bot | |
| E | Relationship | Bot | parent / student / other |
| F | Student Name | Bot | |
| G | Class / Level | Bot | From standard list |
| H | Board | Bot | CBSE / ICSE / State / IB / IGCSE / University / N/A |
| I | Subjects | Bot | Comma-separated |
| J | Mode | Bot | online / home / either |
| K | Area | Bot | Blank for online |
| L | City | Bot | Delhi / Noida / Greater Noida / Gurugram / Ghaziabad / Faridabad |
| M | PIN Code | Bot | |
| N | Preferred Schedule | Bot | Free text, normalised |
| O | Start Date | Bot | `ASAP` or `YYYY-MM-DD` |
| P | Budget Min (₹) | Bot | Number |
| Q | Budget Max (₹) | Bot | Number |
| R | Budget Unit | Bot | per hour / per month |
| S | Goal | Bot | Optional |
| T | Sessions per Week | Bot | Optional |
| U | Tutor Preferences | Bot | Optional, free text |
| V | Notes | Bot | Optional |
| W | Language | Bot | English / Hindi |
| X | Source | Bot | Campaign ID or `organic` |
| Y | Consent At | Bot | `YYYY-MM-DD HH:MM` IST |
| Z | Status | Bot sets `NEW`; ops updates | Dropdown: NEW / IN_REVIEW / TUTOR_SEARCH / MATCHED / CLOSED |
| AA | Assigned To | Ops | |
| AB | Ops Notes | Ops | |
| AC | Last Updated | Ops | |

**Tab `Lists`** — the allowed values for dropdowns (class levels, boards, cities,
statuses), used for data validation in the sheet and by the bot's validator.

### 9.2 Bot working store (not the operational DB)

Conversation state and transcripts change on every message, so they live in the
bot's own small store (e.g. SQLite or Redis), **not** in the sheet:

- **`conversations`** — `id, whatsapp_number, lead_id, state, collected_fields (json), last_inbound_at, last_outbound_at, handoff_flag`
- **`messages`** — `id, conversation_id, direction (in/out), wa_message_id, type, body, created_at`

Leads that end as `STALLED`, `HUMAN_HANDLING` or `CLOSED` before confirmation
stay in this store only.

### 9.3 Future migration

All sheet access goes through a single `LeadRepository` interface
(`append_lead`, `find_by_lead_id`, `delete_older_than`). Moving to a real
database later should mean writing a new implementation of that interface, not
changing conversation logic.

## 10. Constraints

- **Channel:** WhatsApp Business Platform (Cloud API) with an approved business number.
- **Tutee-initiated only:** every conversation is started by the tutee. The bot only replies within WhatsApp's 24-hour window after the tutee's last message and never sends business-initiated messages or message templates (no reminders, re-engagement or broadcasts).
- **Idempotency:** WhatsApp may deliver webhooks more than once — dedupe on `wa_message_id`.
- **Latency:** reply within 5 seconds of an inbound message (p95).
- **Privacy & consent:** collect consent before storing personal data; store only what's needed; support deletion on request; comply with India's DPDP Act. No personal data in logs beyond IDs.
- **Transcript retention:** rows in `messages` (bot store) are deleted **3 months (90 days)** after they were created, by a daily scheduled job. The structured lead must not depend on transcripts after that.
- **Lead retention:** rows in the `Leads` sheet (and matching `conversations` rows in the bot store) are deleted **1 year** after `Created At`, by the same daily job. The consent message should mention this retention period.
- **Google Sheets access:** the bot uses the Google Sheets API through a **service account** that has edit access to that one sheet only. The sheet ID comes from config, never hard-coded. Drive sharing is limited to the operations team — no "anyone with the link" access.
- **Sheet writes:** the bot only **appends** rows; it never edits or deletes rows except for the retention job and deletion requests from tutees. Ops-owned columns (Z status updates onwards, AA–AC) are never overwritten by the bot.
- **Sheet idempotency:** before appending, check whether the Lead ID already exists; retry failed writes with backoff and keep the lead queued in the bot store until the write succeeds, so no confirmed lead is lost.
- **Sheet limits:** stay within Google Sheets API quotas (batch where possible). The sheet is expected to hold one year of leads; revisit the DB choice if it grows beyond ~50,000 rows.
- **Languages:** English and Hindi only in v1.
- **Serviceable area:** home tuition in Delhi/NCR only; online tuition has no location limit.
- **LLM use:** the language model handles conversation and extraction, but field values are validated by code against allowed lists before saving. The DB write happens only from validated, confirmed data — never directly from raw model output.
- **Safety:** detect minors chatting alone and keep the conversation strictly to requirements; route abusive or sensitive content to a human.

## 11. Success criteria

v1 is done when:

- [ ] ≥ 90% of completed leads have every required field filled and valid
- [ ] Median conversation to complete a lead is ≤ 8 bot messages
- [ ] Tutees are never asked for a detail they have already provided (verified in test transcripts)
- [ ] ≥ 60% of conversations that start end as `NEW` leads
- [ ] Leads appear in the Google Sheet within 10 seconds of tutee confirmation
- [ ] Duplicate webhooks never create duplicate leads (rows) or messages
- [ ] A temporary Google API failure never loses a confirmed lead
- [ ] A tutee can reach a human at any point by asking

## 12. Key decisions (and why)

| # | Decision | Reason |
|---|---|---|
| D1 | LLM for conversation + extraction, code for validation and DB writes | Natural conversation without letting the model corrupt data |
| D2 | Explicit confirmation step before saving | Catches extraction errors; builds trust |
| D3 | Separate `conversations` and `leads` tables | A parent may request tutors for two children from one number |
| D4 | Location required only for home tuition | Avoids asking unnecessary personal details |
| D5 | Budget is a required field | Operations needs it to shortlist tutors without re-contacting the tutee |
| D6 | Out-of-area home requests are offered online first | Keeps the lead instead of losing it |
| D7 | Transcripts kept 3 months; leads kept 1 year | Limits stored personal data while keeping what ops needs |
| D8 | Bot never quotes budget ranges | Pricing is not the bot's call; avoids setting wrong expectations |
| D9 | Google Sheet as the operational DB for v1 | Ops team can use it immediately with no admin tools to build |
| D10 | Conversation state and transcripts kept outside the sheet | They change on every message; the sheet would hit API limits and clutter the ops view |
| D11 | All sheet access behind a `LeadRepository` interface | Makes the later move to a real database a contained change |

## 13. Open questions

None at present.

**Resolved (2026-09-29):** home tuition limited to Delhi/NCR · budget required,
no ranges suggested by the bot · ops team works every day 10 AM–5 PM IST ·
languages English and Hindi · transcripts retained 3 months · leads retained 1 year ·
operational DB is a native Google Sheet on Google Drive for now.

## 14. Guidance for AI agents working on this repo

- Read this file before starting any task.
- Do not build anything listed under **Non-goals**.
- Never write to the `Leads` sheet from unvalidated model output, and never overwrite ops-owned columns.
- Access the sheet only through `LeadRepository`; don't call the Sheets API from conversation code.
- Any change to required fields (§6) or the lifecycle (§8) needs human approval.
- Tie pull requests to a goal ID (e.g. `G3: multi-field extraction from one message`).
- If a requirement is unclear, add it to **Open questions** instead of inventing an answer.

