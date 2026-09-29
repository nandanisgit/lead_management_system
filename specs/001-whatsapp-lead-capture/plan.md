# Implementation Plan: WhatsApp Lead Capture

**Branch**: `001-whatsapp-lead-capture` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-whatsapp-lead-capture/spec.md`

## Summary

A single Python web service receives WhatsApp Cloud API webhooks, runs a
human-like requirement conversation with each tutee and records confirmed leads
in the operations Google Sheet. Claude is used for two narrow jobs per turn —
extracting candidate field values through a forced tool call, and phrasing the
next reply — while code owns the conversation state machine, validation
against allowed lists, the out-of-area and budget rules, and every write.
Confirmed leads go through a local outbox so they are recorded exactly once
even if Google is briefly unavailable. Scheduled jobs handle stalled
conversations, handoff sync and retention. Conversation quality is verified by
an eval suite in which a simulated tutee answers from known facts, scored
against the spec's success criteria; latency and exactly-once targets are
verified by load tests (capacity, burst, soak). The design keeps seams
(`LeadRepository`, `TurnQueue`, `ConversationLock`, SQLAlchemy) so it can scale
out later without rewriting the conversation logic.
(Decisions: [research.md](research.md).)

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI + Uvicorn, Pydantic v2, SQLAlchemy 2 + Alembic, `anthropic` SDK, `google-api-python-client` + `google-auth`, `httpx` (WhatsApp Cloud API), APScheduler, Typer (CLI)

**Storage**: SQLite (WAL) for the bot working store; native Google Sheet as the operational lead register

**Testing**: pytest (+ pytest-asyncio, respx for HTTP fakes); eval runner in `evals/` with a simulated tutee (real model under test); Locust load profiles in `load/`

**Target Platform**: Linux server, one Docker container behind HTTPS

**Project Type**: web service (webhook backend) with a CLI for operations tasks

**Performance Goals**: reply within 5 s p95 (SC-005); lead visible in sheet within 10 s of confirmation (SC-006); webhook acknowledged within 1 s

**Constraints**: WhatsApp 24-hour window and template rules; Sheets API quotas; no personal data in logs; English/Hindi only; home tuition Delhi/NCR only; ops hours 10 AM–5 PM IST daily

**Scale/Scope**: up to a few hundred conversations per day; ≤ ~50,000 lead rows per year; single instance. Assumed peak for load testing: 30 tutees chatting at once and 5 inbound messages/second for 10 minutes (research R13). Scaling path beyond v1: research R14.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | How this plan complies | Pre-research | Post-design |
|---|---|---|---|
| I. Intent is the source of truth | Every user story maps to G1–G7; nothing from Non-goals (no matching, pricing, scheduling, broadcasts). Required fields and lifecycle match intent §6 and §8. | ✅ | ✅ |
| II. Validated data only | Model output is a proposal via `record_requirements`; the `Requirement` Pydantic model validates against `config/lists.yaml`; only `confirming → completed` creates an outbox row; sheet access only via `LeadRepository`; append-only A–Z, never AA–AC. | ✅ | ✅ |
| III. Test-first, eval-backed | pytest for deterministic code with fakes; simulated-tutee eval suite with checks mapped to SC-001/002/003/008; load profiles verify SC-005/006/007 before release; CI gates on tests and evals. | ✅ | ✅ |
| IV. Privacy and consent | Consent before collection (`awaiting_consent` state); retention jobs 90 days / 1 year; deletion on request; logs carry IDs only; secrets via env; service account scoped to one sheet. | ✅ | ✅ |
| V. Small, reversible steps | One service, one DB file, no external queue; outbox and per-number locks give idempotency; dedupe on `wa_message_id` and Lead ID. | ✅ | ✅ (one justified deviation below) |

**Result**: PASS. One item recorded under Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-whatsapp-lead-capture/
├── plan.md              # This file
├── research.md          # Phase 0 decisions
├── data-model.md        # Entities, validation, lifecycle, retention
├── quickstart.md        # Setup and validation scenarios
├── contracts/
│   ├── whatsapp-webhook.md   # Inbound webhook + outbound sender
│   ├── lead-sheet.md         # Google Sheet tabs + LeadRepository interface
│   └── llm-extraction.md     # Extraction tool schema + reply guards
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
src/lead_capture/
├── app.py                  # FastAPI app, routes wiring, startup checks
├── config.py               # Settings from environment
├── cli.py                  # Typer CLI: chat, eval, check-sheet, sync-lists, replay, jobs
├── domain/
│   ├── requirement.py      # Requirement model + validators
│   ├── lists.py            # Loads config/lists.yaml
│   ├── ids.py              # Lead / handoff ID generation
│   └── hours.py            # IST ops-hours logic for closing messages
├── webhook/
│   ├── routes.py           # GET/POST /webhooks/whatsapp, /healthz
│   ├── signature.py        # X-Hub-Signature-256 check
│   └── parser.py           # Payload → inbound events
├── whatsapp/
│   └── sender.py           # WhatsAppSender (Cloud API) + FakeSender
├── conversation/
│   ├── engine.py           # One turn: load → extract → validate → decide → reply
│   ├── states.py           # Lifecycle state machine
│   ├── planner.py          # Missing fields → next instruction
│   ├── llm.py              # Claude client: extraction + reply calls
│   ├── guards.py           # Question/word/currency/language checks
│   ├── dispatcher.py       # Debounce, pulls turns from TurnQueue
│   ├── turn_queue.py       # TurnQueue interface + in-process asyncio impl
│   └── locks.py            # ConversationLock interface + in-memory impl
├── store/
│   ├── db.py               # Engine/session
│   ├── models.py           # Contact, Conversation, Message, LeadOutbox
│   └── queries.py
├── sheet/
│   ├── repository.py       # LeadRepository protocol + errors
│   ├── google_sheet.py     # GoogleSheetLeadRepository
│   └── in_memory.py        # InMemoryLeadRepository
└── jobs/
    ├── scheduler.py        # APScheduler setup (Asia/Kolkata)
    ├── outbox.py           # Drain outbox → sheet
    ├── stalled.py          # 24 h → stalled
    ├── handoffs.py         # Sync Resolved handoffs
    └── retention.py        # 90-day / 1-year deletion

prompts/assistant.md        # System prompt (tone, language, rules)
config/lists.yaml           # Allowed values
migrations/                 # Alembic
evals/
├── scenarios/*.yaml        # Tutee facts, style, expected outcome
├── tutee.py                # Simulated tutee (small Claude model)
├── checks.py               # SC-mapped scoring
└── runner.py
load/
├── locustfile.py           # capacity / burst / soak profiles
├── signing.py              # Signed webhook payload builder
└── reports/
tests/
├── unit/                   # domain, planner, guards, states, ids, hours
├── contract/               # webhook payloads, sheet contract, extraction schema
└── integration/            # full turns with fakes; outbox; retention
Dockerfile
pyproject.toml
.env.example
.github/workflows/ci.yml    # lint + tests on PR; evals on conversation changes
```

**Structure Decision**: single project (`src/` layout) — one deployable
service with a CLI. No frontend: the operations team works in the Google Sheet.

## Implementation Phases (input for /speckit-tasks)

1. **Foundation** — project skeleton, settings, SQLite models + migrations, `config/lists.yaml`, `Requirement` validation, IDs, ops-hours logic, CI.
2. **US1 core (MVP)** — webhook verify/receive/dedupe, sender, extraction + reply calls, state machine and planner, summary/confirmation, outbox + `GoogleSheetLeadRepository`, closing message by time of day, local `chat` CLI, first eval scenarios.
3. **US2** — resume and recap, stalled job, multiple students per number, duplicate-lead prevention.
4. **US3** — out-of-area flow, unsupported language, not interested / STOP.
5. **US4** — handoff triggers, `Handoffs` tab, silence during handoff, echo handling, resolution sync.
6. **US5** — consent gate, deletion on request, retention jobs.
7. **Polish** — non-text messages, burst debounce tuning, guard fallbacks, full eval suite, Dockerfile and deploy docs.
8. **Verify under load** — Locust profiles (`capacity`, `burst`, `soak`) with the simulated tutee, stubbed-model mode, lead reconciliation report; run before release.

The `TurnQueue` and `ConversationLock` interfaces are built in phase 2 (US1), not later, so the scaling path in research R14 needs no rework of the engine.

## Scaling Path

Summarised from [research.md R14](research.md). v1 is one process; each later
step is triggered by a measured limit, not done up front.

1. **Tune model calls** (first limit: Claude latency / rate limits).
2. **Move leads off the Sheet** to PostgreSQL and/or a CRM via a new `LeadRepository` implementation.
3. **PostgreSQL for the bot store** (config change).
4. **Scale out**: stateless webhook receivers → queue partitioned by WhatsApp number → autoscaled workers; jobs in one worker or cron.
5. **Operate at scale**: tenants, metrics and alerts, model fallback route.

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| A `Handoffs` tab in the operations sheet holds handoff events (constitution/intent keep conversation state out of the sheet) | FR-024 requires handed-over conversations to be visible to the ops team, who work only in the sheet | Email alerts are easy to miss and give no "resolved" signal; a shared inbox product adds cost. The tab holds only a notification row and a Resolved flag — the conversation state itself stays in the bot store. |
