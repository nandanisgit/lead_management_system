---
description: "Task list for 001-whatsapp-lead-capture"
---

# Tasks: WhatsApp Lead Capture

**Input**: Design documents from `/specs/001-whatsapp-lead-capture/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The constitution (Principle III) requires tests written first
and failing before implementation, and evals for conversation behaviour.

**Organization**: Tasks are grouped by user story so each story can be built,
tested and demonstrated on its own. Every performance/cost number comes from
`config/settings.yaml` and every external service is reached through a port
(constitution Principle VI, research R16) — no task may hard-code either.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: user story from spec.md (US1–US5)
- Paths are relative to the repository root (single project, `src/` layout)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: project skeleton, tooling and CI

- [X] T001 Create `pyproject.toml` for package `lead-capture` (Python 3.12, `src/` layout, console script `lead-capture = lead_capture.cli:app`) with dependencies fastapi, uvicorn, pydantic, pydantic-settings, pyyaml, sqlalchemy, alembic, anthropic, google-api-python-client, google-auth, httpx, apscheduler (3.x), typer; dev dependencies pytest, pytest-asyncio, respx, freezegun, ruff, locust; generate `uv.lock` with `uv sync`
- [X] T002 Create the directory tree from plan.md (`src/lead_capture/{ports,adapters/llm,adapters/channels/whatsapp_cloud,adapters/leads,domain,conversation,store,costs,jobs}`, `config/`, `prompts/`, `migrations/`, `evals/scenarios`, `evals/reports`, `load/reports`, `tests/{unit,contract,integration}`) with `__init__.py` files where needed
- [X] T003 [P] Configure ruff (lint + format, line length 100) in `pyproject.toml`
- [X] T004 [P] Configure pytest (asyncio mode auto, markers `eval` and `load` excluded by default) in `pyproject.toml` and add shared fixtures stub in `tests/conftest.py`
- [X] T005 [P] Create `.env.example` listing every secret from quickstart.md (`ANTHROPIC_API_KEY`, `WA_PHONE_NUMBER_ID`, `WA_ACCESS_TOKEN`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN`, `WA_API_VERSION`, `LEAD_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE`, `LOAD_TEST_SHEET_ID`, `DATABASE_URL`) with placeholder values only
- [X] T006 [P] Extend `.gitignore` with `data/`, `evals/reports/*`, `load/reports/*` (keep `.gitkeep`), `.venv/`
- [X] T007 [P] Create CI workflow `.github/workflows/ci.yml`: on pull request run `uv sync`, `ruff check`, `ruff format --check`, `pytest`; run `lead-capture eval --pr-subset` only when files under `src/lead_capture/conversation/`, `src/lead_capture/adapters/llm/`, `prompts/`, `config/settings.yaml` or `evals/` change (secrets from repository settings)
- [X] T008 [P] Create nightly workflow `.github/workflows/nightly-evals.yml` running the full eval suite on `main` and uploading `evals/reports/` as an artifact

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: settings, ports, fake adapters, domain model, store, app and CLI skeleton — everything every story needs

**⚠️ CRITICAL**: no user story work starts until this phase is complete

### Settings and registry

- [X] T009 Create `config/settings.yaml` containing every key and default from research.md R16 "Configurable parameters" (llm, conversation, channel, leads, ops, retention, jobs, costs, evals, load groups), each with a one-line comment giving the reason
- [X] T010 Write failing tests in `tests/unit/test_settings.py`: defaults load from `config/settings.yaml`; `LC__LLM__REPLY_MODEL` style env vars override nested keys; invalid values (negative timeouts, `context_messages < 1`, unknown provider names, `hours_start >= hours_end`) raise at start-up
- [X] T011 Implement `src/lead_capture/settings.py`: Pydantic settings model mirroring `config/settings.yaml` with validation, env override (prefix `LC__`, nested delimiter `__`), secrets read only from environment, `settings.effective()` returning a dict for reports
- [X] T012 Write failing tests in `tests/unit/test_registry.py`: `build_llm(settings)`, `build_channel(settings)`, `build_lead_repository(settings)`, `build_queue`, `build_lock`, `build_clock` return the adapter named in settings; unknown names raise a clear error
- [X] T013 Implement `src/lead_capture/registry.py` mapping provider names (`anthropic`, `fake`, `stub`; `whatsapp_cloud`, `fake`; `google_sheet`, `in_memory`; `inprocess`; `memory`; `system`, `frozen`) to adapter factories

### Ports (interfaces and normalised types)

- [X] T014 [P] Define `LLMClient` protocol (`async extract(turn: TurnContext) -> ExtractionResult`, `async write_reply(turn: TurnContext, instruction: Instruction) -> ReplyResult`) and types `TurnContext`, `ExtractionResult` (fields + signals exactly as in contracts/llm-extraction.md), `ReplyResult`, `TokenUsage(model, input, output, cache_read, cache_write)` in `src/lead_capture/ports/llm.py`
- [X] T015 [P] Define `MessagingChannel` protocol (`verify_subscription`, `async parse_inbound(request) -> list[InboundEvent]`, `async send(to, OutboundMessage) -> SentMessage`, `capabilities: Capabilities`) and types `InboundMessage` (id, from, type, text, choice_id, referral_source, profile_name, timestamp, is_echo), `OutboundMessage` (text | choices), `Choice(id, title)`, `Capabilities(max_buttons, max_list_rows, has_service_window, window_hours)` — no template support (FR-022) in `src/lead_capture/ports/channel.py`
- [X] T016 [P] Define `LeadRepository` protocol with the methods in contracts/lead-sheet.md (`append_lead`, `exists`, `delete_lead`, `delete_leads_created_before`, `append_handoff`, `resolved_handoffs`, `delete_handoffs_before`, `sync_lists`, `check_headers`), types `LeadRow` (columns A–Z), `HandoffRow` (A–G), and errors `RepositoryUnavailable`, `RepositoryContractError` in `src/lead_capture/ports/leads.py`
- [X] T017 [P] Define `TurnQueue` (`put(contact_key, item)`, per-key ordered consumption), `ConversationLock` (async context manager per contact key) and `Clock` (`now()` timezone-aware) protocols in `src/lead_capture/ports/queue.py`, `src/lead_capture/ports/locks.py`, `src/lead_capture/ports/clock.py`

### Shared contract test suites (every adapter must pass them)

- [X] T018 [P] Write reusable contract suite `tests/contract/llm_client_suite.py` (returns `ExtractionResult` with only schema fields, reports `TokenUsage`, respects `max_output_tokens`, raises a typed error on timeout) and run it against the fake in `tests/contract/test_llm_fake.py`
- [X] T019 [P] Write reusable contract suite `tests/contract/channel_suite.py` (inbound normalisation, echo flag, duplicate IDs preserved, `send` returns an ID, choices degrade to numbered text when `max_buttons == 0`) and run it against the fake in `tests/contract/test_channel_fake.py`
- [X] T020 [P] Write reusable contract suite `tests/contract/lead_repository_suite.py` (idempotent `append_lead`, never writes AA–AC, formula-injection guard for values starting with `=`, `+`, `-`, `@`, delete by Lead ID, handoff resolved listing, header check) and run it against the in-memory adapter in `tests/contract/test_leads_in_memory.py`
- [X] T021 [P] Write tests `tests/contract/test_queue_lock_clock.py`: per-key ordering, lock exclusivity per contact, frozen clock

### Fake and in-process adapters

- [X] T022 [P] Implement `FakeLLMClient` (scripted results per call, records calls and usage) in `src/lead_capture/adapters/llm/fake.py`
- [X] T023 [P] Implement `FakeChannel` (in-memory outbox of sent messages, configurable capabilities) in `src/lead_capture/adapters/channels/fake.py`
- [X] T024 [P] Implement `InMemoryLeadRepository` in `src/lead_capture/adapters/leads/in_memory.py`
- [X] T025 [P] Implement in-process `TurnQueue` (asyncio, one worker task per active contact key) in `src/lead_capture/adapters/queue_inprocess.py`, in-memory `ConversationLock` in `src/lead_capture/adapters/locks_memory.py`, `SystemClock`/`FrozenClock` (zone from `ops.timezone`) in `src/lead_capture/adapters/clock.py`

### Domain

- [X] T026 [P] Create the allowed-value lists (now `lists:` in `config/requirement.yaml`, see T083) with `grade_levels` (`Class 1`…`Class 12`, `Undergraduate`, `Postgraduate`, `Adult`), `boards` (`CBSE`, `ICSE`, `State`, `IB`, `IGCSE`, `University`, `N/A`), `subjects`, `cities` (`Delhi`, `Noida`, `Greater Noida`, `Gurugram`, `Ghaziabad`, `Faridabad`), NCR PIN code ranges, `modes` (`online`, `home`, `either`), `budget_units` (`per_hour`, `per_month`), `goals`, `lead_statuses` (`NEW`, `IN_REVIEW`, `TUTOR_SEARCH`, `MATCHED`, `CLOSED`), `minor_grade_levels` (`Class 1`…`Class 12`, FR-029), `guardian_relationships` (`mother`, `father`, `guardian`, `other`)
- [X] T027 [P] Load and validate the allowed values (now part of `RequirementSchema` in `src/lead_capture/domain/schema.py`, see T083)
- [X] T028 Write failing tests `tests/unit/test_requirement.py` covering every rule in data-model.md "Value object: Requirement" (see T029) including cross-field rules and the `either`-outside-NCR → `online` rule
- [X] T029 Implement `Requirement` Pydantic model in `src/lead_capture/domain/requirement.py` with these constraints verbatim from data-model.md: `contact_name` "1–60 chars"; `relationship` "`parent` / `student` / `other`"; `student_name` "1–60 chars; defaults to `contact_name` when `relationship = student`"; `grade_level` "one of `lists.grade_levels`"; `board` required "if grade is a school class", "one of `CBSE`, `ICSE`, `State`, `IB`, `IGCSE`; `University` / `N/A` otherwise"; `subjects` "1–5 items from `lists.subjects`"; `mode` "`online` / `home` / `either`"; `area` "if mode ≠ `online`", "2–80 chars"; `city` "if mode ≠ `online`", "one of the six NCR cities"; `pincode` optional "6 digits; if given, must fall in NCR PIN ranges when mode ≠ `online`"; `schedule` "3–120 chars"; `start_date` "`ASAP` or a date from today to +180 days"; `budget_min`, `budget_max` "positive integers in ₹; `min ≤ max`; a single figure sets both"; `budget_unit` "`per_hour` / `per_month`"; `goal` optional "≤ 120 chars"; `sessions_per_week` optional "1–7"; `tutor_preferences` optional "≤ 200 chars"; `level_notes` optional "≤ 300 chars"; `email` optional "valid email"; `guardian_name` "if `minor_alone`" "1–60 chars"; `guardian_relationship` "if `minor_alone`" "`mother` / `father` / `guardian` / `other`"; plus `missing_required()` and `merge(partial)` (latest value wins, invalid values rejected with a reason)
- [X] T030 [P] Write tests then implement Lead ID `L-YYYYMMDD-XXXX` and Handoff ID `H-YYYYMMDD-XXXX` ("`XXXX` = 4 random base32 chars") in `tests/unit/test_ids.py` and `src/lead_capture/domain/ids.py`
- [X] T031 [P] Write tests then implement ops-hours logic (`today` / `after 10 AM today` / `after 10 AM tomorrow` from `ops.hours_start`, `ops.hours_end`, `ops.timezone`, every day) in `tests/unit/test_hours.py` and `src/lead_capture/domain/hours.py`

### Store

- [X] T032 Write failing tests `tests/integration/test_store.py`: `wa_message_id` unique; only one conversation per (`contact_id`, `student_key`) in `in_progress`, `confirming`, `stalled` or `handed_over`; `lead_outbox.lead_id` primary key; timestamps stored in UTC
- [X] T033 Implement `src/lead_capture/store/db.py` (SQLAlchemy 2 engine from `DATABASE_URL`, SQLite WAL mode, session factory)
- [X] T034 Implement models `Contact`, `Conversation`, `Message`, `LeadOutbox` exactly as data-model.md, plus `UsageEvent` (`conversation_id`, `kind` = `extract` / `reply` / `message_out`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `created_at`) for cost tracking (research R15), in `src/lead_capture/store/models.py`; add `UsageEvent` to data-model.md
- [X] T035 Initialise Alembic in `migrations/` and create the first migration for all tables and constraints
- [X] T036 [P] Implement common queries (get-or-create contact, active conversation for contact + student, store message idempotently, record usage) in `src/lead_capture/store/queries.py`

### App, logging, CLI, prompt

- [X] T037 [P] Write test then implement logging setup that emits JSON with IDs only and a filter that drops message bodies, names and phone numbers (FR-027) in `tests/unit/test_logging.py` and `src/lead_capture/logging.py`
- [X] T038 Implement `src/lead_capture/app.py`: build adapters via registry at start-up, run `leads.check_headers()` (skip for in-memory), mount channel routes at `/webhooks/{channel}`, `GET /healthz` returning `{"status","db","outbox_pending"}` with no personal data
- [X] T039 [P] Implement Typer app skeleton in `src/lead_capture/cli.py` with command groups `chat`, `eval`, `load`, `costs`, `check-sheet`, `sync-lists`, `replay`, `jobs` (stubs that print "not implemented")
- [X] T040 [P] Write the system prompt `prompts/assistant.md` from intent §7: tone, English/Hindi/Hinglish mirroring, max questions and words (as placeholders filled from settings), never suggest budget ranges, off-topic handling, "talk to a person" always available

**Checkpoint**: `uv run pytest` passes; the app starts with fake adapters; nothing talks to a real service yet

---

## Phase 3: User Story 1 — Tutee describes their need and a complete lead is recorded (Priority: P1) 🎯 MVP

**Goal**: consent → natural conversation → summary → confirmation → lead in the Google Sheet with status `NEW` → correct closing message

**Independent Test**: scripted WhatsApp conversation from consent to confirmation produces exactly one `NEW` row with every required field and the right closing message (quickstart scenarios 1–3)

### Tests for User Story 1 (write first, must fail)

- [X] T041 [P] [US1] Contract tests for WhatsApp webhook: GET verify (`hub.mode`, `hub.verify_token`, `hub.challenge` → 200 / 403), POST signature `X-Hub-Signature-256` (valid → 200, missing/wrong → 401), payload parsing of text, `button_reply`, `list_reply`, `referral`, `contacts[].profile.name`, echoes and `statuses` using fixtures in `tests/contract/fixtures/whatsapp/*.json` in `tests/contract/test_whatsapp_cloud_channel.py` (also runs `channel_suite`)
- [X] T042 [P] [US1] Contract test for outbound mapping: text; ≤ 3 choices → reply buttons; 4–10 choices → interactive list; no template method exists; retries on 429/5xx up to `channel.max_retries` (respx) in `tests/contract/test_whatsapp_cloud_send.py`
- [X] T043 [P] [US1] Contract test for `AnthropicLLMClient` with mocked HTTP: forced `record_requirements` tool call and schema exactly as contracts/llm-extraction.md, models from `llm.extraction_model` / `llm.reply_model`, `llm.max_output_tokens`, prompt caching on system prompt + tool schema when `llm.prompt_cache`, transcript trimmed to `llm.context_messages`, timeout and retries, `TokenUsage` returned (also runs `llm_client_suite`) in `tests/contract/test_anthropic_llm_client.py`
- [X] T044 [P] [US1] Contract test for `GoogleSheetLeadRepository` with mocked Sheets API: header check, append range `Leads!A:Z` with `INSERT_ROWS` / `USER_ENTERED`, Lead ID lookup before append, `'` prefix for WhatsApp number and formula-like values, never touches AA–AC, 429/5xx → `RepositoryUnavailable` (also runs `lead_repository_suite`) in `tests/contract/test_google_sheet_repository.py`
- [X] T045 [P] [US1] Unit tests for the planner: missing-field order "consent → contact_name & relationship → student_name → grade_level & board → subjects → mode → area & city → schedule → start_date → budget → guardian_name & guardian_relationship (only if `minor_alone`) → (optional fields if the conversation allows) → summary", grouping, at most `conversation.max_questions_per_message` fields per ask, in `tests/unit/test_planner.py`
- [X] T046 [P] [US1] Unit tests for guards: question count, word count, currency amounts not stated by the tutee (₹, Rs, INR, "rupees", digits with currency), language mismatch; regeneration up to `llm.max_regenerations` then fixed text, in `tests/unit/test_guards.py`
- [X] T047 [P] [US1] Unit tests for state transitions `awaiting_consent → in_progress → confirming → completed` and `confirming → in_progress` on correction; only `confirming → completed` creates an outbox row, in `tests/unit/test_states.py`
- [X] T048 [P] [US1] Unit tests for fixed texts and deterministic-turn detection (button taps, greeting/consent, summary, closing) — no `LLMClient` call when `llm.skip_for_deterministic_turns` is true, model call when false, in `tests/unit/test_fixed_texts.py`
- [X] T049 [US1] Integration test, happy path with fakes: "Hi, need a maths tutor for my son" → consent → answers → summary → confirm → one `NEW` lead row, closing text matches time of day (frozen clock at 15:00, 19:00, 08:00 IST) in `tests/integration/test_us1_happy_path.py`
- [X] T050 [P] [US1] Integration test: one message with class, board, two subjects, mode, area, schedule → all captured, only missing fields asked; never re-asks a captured field, in `tests/integration/test_us1_multi_field.py`
- [X] T051 [P] [US1] Integration test: correction at summary ("change timing to weekends") → revised summary → confirm, in `tests/integration/test_us1_correction.py`
- [X] T052 [P] [US1] Integration test: budget unsure → assistant asks for an approximate figure, no amount suggested; Hindi/Hinglish reply language mirrored, in `tests/integration/test_us1_budget_language.py`
- [X] T053 [P] [US1] Integration test: duplicate webhook delivery → one stored message, one reply, one lead; sheet unavailable at confirmation → tutee still gets confirmation, lead synced after recovery, never duplicated, in `tests/integration/test_us1_idempotency_outbox.py`
- [X] T054 [P] [US1] Integration test for minors (FR-029): a Class 9 student chatting for themselves → strict mode (off-topic messages get a one-line redirect only), guardian name and relationship asked before the summary, `consent_by_minor` set, summary asks the student to share it with their parent or guardian, lead Notes (column V) start with `MINOR – consent given by student – contact parent/guardian: <name> (<relationship>)`; a parent chatting for a Class 9 child → no guardian question; the model's `likely_minor_alone` signal alone also triggers the rule, in `tests/integration/test_us1_minor_alone.py`
- [X] T055 [P] [US1] Integration test for off-topic handling (FR-007): a fees or tutor-name question → fixed "our team will share this" text plus the next requirement question, no model call; a safe general off-topic question → at most `conversation.off_topic_max_sentences` sentence(s) then the next question; strict mode (FR-029) → one-line redirect only, in `tests/integration/test_us1_off_topic.py`
- [X] T056 [P] [US1] Integration test for turn limits (FR-030): exceeding `conversation.max_turns_per_contact_per_hour` or `_per_day` → exactly one fixed notice, `Contact.rate_limited_until` set, then no replies and no `LLMClient` calls for that number until the period passes; other numbers unaffected; event logged with IDs only, in `tests/integration/test_us1_rate_limit.py`

### Implementation for User Story 1

- [X] T057 [P] [US1] Implement signature verification (HMAC-SHA256 of raw body with `WA_APP_SECRET`) in `src/lead_capture/adapters/channels/whatsapp_cloud/signature.py`
- [X] T058 [P] [US1] Implement payload parser → `InboundMessage` list (text, interactive replies, unsupported types, referral `source_id`, profile name, echoes) in `src/lead_capture/adapters/channels/whatsapp_cloud/parser.py`
- [X] T059 [P] [US1] Implement Cloud API sender (httpx, `WA_API_VERSION`, `channel.send_timeout_seconds`, retries with backoff up to `channel.max_retries`, error class + conversation ID only in logs) in `src/lead_capture/adapters/channels/whatsapp_cloud/sender.py`
- [X] T060 [US1] Implement `WhatsAppCloudChannel` combining T057–T059, declaring capabilities (3 buttons, 10 list rows, 24-hour service window) and FastAPI routes for GET verify / POST events (ack within 1 s, then enqueue) in `src/lead_capture/adapters/channels/whatsapp_cloud/channel.py`
- [X] T061 [US1] Implement inbound handling: store message idempotently on `wa_message_id`, update contact profile name and conversation `source`, put a turn on `TurnQueue` (echoes stored, never enqueued) in `src/lead_capture/conversation/inbound.py`
- [X] T062 [US1] Implement dispatcher: consume `TurnQueue`, hold `ConversationLock` per contact, debounce `conversation.debounce_ms` so bursts become one turn, call the engine in `src/lead_capture/conversation/dispatcher.py`
- [X] T063 [P] [US1] Implement lifecycle state machine for US1 states in `src/lead_capture/conversation/states.py`
- [X] T064 [P] [US1] Implement planner → `Instruction` (`ASK: …`, `SUMMARISE_AND_CONFIRM`, `CLOSE_COMPLETED(when)`) in `src/lead_capture/conversation/planner.py`
- [X] T065 [P] [US1] Implement English and Hindi fixed texts (greeting + consent with retention periods from settings, summary lead-in, closing messages, clarifying questions for rejected values) and deterministic-turn detection in `src/lead_capture/conversation/fixed_texts.py`
- [X] T066 [P] [US1] Implement guards with limits from settings in `src/lead_capture/conversation/guards.py`
- [X] T067 [P] [US1] Implement `AnthropicLLMClient` (tool schema from `Requirement`, prompt caching, `llm.*` settings, semaphore of `llm.max_concurrent_calls`, timeout `llm.timeout_seconds`, retries `llm.max_retries`, returns `TokenUsage`) in `src/lead_capture/adapters/llm/anthropic.py`
- [X] T068 [US1] Implement the engine turn: load state → deterministic shortcut or `LLMClient.extract` → `Requirement.merge` → planner → fixed text or `LLMClient.write_reply` → guards → `MessagingChannel.send` (choices for consent, mode, board, confirm) → record `UsageEvent`s, in `src/lead_capture/conversation/engine.py`
- [X] T069 [US1] Implement summary builder from validated values (EN/HI) and confirmation handling; on confirm create `LeadOutbox` row with `LeadRow` A–Z values in the same transaction as `confirming → completed`, in `src/lead_capture/conversation/summary.py`
- [X] T070 [US1] Implement FR-029: set `Conversation.minor_alone` when `relationship = student` and `grade_level` is in `lists.minor_grade_levels`, or on the `likely_minor_alone` signal; add `ASK_GUARDIAN` instruction and `strict` flag to the planner; set `Conversation.consent_by_minor` when consent preceded detection; EN/HI fixed texts for the guardian question, the one-line redirect and the "please share this with your parent" summary line; prefix lead Notes with the minor marker, in `src/lead_capture/conversation/minors.py`, `src/lead_capture/conversation/planner.py`, `src/lead_capture/conversation/fixed_texts.py` and `src/lead_capture/conversation/summary.py`
- [X] T071 [US1] Implement FR-007: handle `off_topic` and `asks_fees_or_tutors` signals with `ANSWER_OFF_TOPIC_AND_STEER(next_ask)` and `FEES_OR_TUTORS_AND_STEER(next_ask)` instructions (combined with the next question in one message), EN/HI fixed texts, strict-mode redirect reuse, in `src/lead_capture/conversation/planner.py` and `src/lead_capture/conversation/fixed_texts.py`
- [X] T072 [US1] Implement FR-030 turn limiter checked by the dispatcher before the engine runs: count inbound turns per contact over the last hour/day from `Message` rows, compare with settings, send the `RATE_LIMITED` fixed text once, set `Contact.rate_limited_until`, skip engine and model calls while limited, in `src/lead_capture/conversation/rate_limit.py` and `src/lead_capture/conversation/dispatcher.py`
- [X] T073 [P] [US1] Implement `GoogleSheetLeadRepository` (service account from `GOOGLE_SERVICE_ACCOUNT_FILE`, sheet `LEAD_SHEET_ID`, methods for `Leads` and `Lists` tabs; handoff methods may raise `NotImplementedError` until US4) in `src/lead_capture/adapters/leads/google_sheet.py`
- [X] T074 [US1] Implement outbox drain (immediate trigger after confirmation plus every `leads.outbox_interval_seconds`, exponential backoff capped at `leads.max_backoff_seconds`, mark `synced`) in `src/lead_capture/jobs/outbox.py`
- [X] T075 [US1] Implement APScheduler setup with time zone `ops.timezone`, registering the outbox job, started from `app.py`, in `src/lead_capture/jobs/scheduler.py`
- [X] T076 [P] [US1] Implement CLI `chat` (terminal conversation with real engine, `FakeChannel`, in-memory repository; `--sheet` uses the real sheet), `check-sheet`, `sync-lists` (with `--dry-run`) and `replay <file>` in `src/lead_capture/cli.py`

### Evals for User Story 1

- [X] T077 [US1] Implement simulated tutee (answers only from `tutee_facts`, in the scenario's style, model `evals.tutee_model`) in `evals/tutee.py`
- [X] T078 [US1] Implement checks mapped to SC-001 (lead equals facts), SC-002 (≤ 8 bot messages), SC-003 (no re-ask, no suggested amount), FR-001/002 (≤ 2 questions, language), expected outcome, plus token usage and estimated cost per run, in `evals/checks.py`
- [X] T079 [US1] Implement runner (`evals.repeats`, `evals.pass_threshold`, `--scenario`, `--pr-subset`, `--model`, report with effective settings to `evals/reports/<timestamp>.md`, non-zero exit below threshold) and wire `lead-capture eval` in `evals/runner.py` and `src/lead_capture/cli.py`
- [X] T080 [P] [US1] Write scenarios `evals/scenarios/us1_*.yaml`: English parent happy path, Hinglish home tuition in Dwarka, multi-field first message, correction at summary, budget unsure, Hindi-only tutee, student chatting for self
- [X] T081 [P] [US1] Write eval scenario `evals/scenarios/us1_minor_alone.yaml`: Class 9 student chatting alone in Hinglish, asks an off-topic question mid-way; expected: guardian details captured, strict redirect, lead marked as minor
- [X] T082 [P] [US1] Write eval scenario `evals/scenarios/us1_off_topic.yaml`: parent asks about fees and a specific tutor mid-conversation and makes small talk; expected: short fixed answer, steer back, no amount suggested, lead completed

### Review follow-up (2026-09-30): no hard-coding, documentation

- [X] T083 [US1] Define every tutor-requirement field once in `config/requirement.yaml` (types, allowed values, required-when conditions, questions, labels, model hints, summary lines, sheet layout); load and validate it in `src/lead_capture/domain/schema.py`; generic per-type validators in `src/lead_capture/domain/field_types.py`; `Requirement` in `src/lead_capture/domain/requirement.py` driven by config; model tool schema, questions, tap options, summary, lead row, sheet layouts, Lists tab and eval checks generated from it; `config/lists.yaml` removed
- [X] T084 [US1] Test that a field can be added or removed through config only, and that inconsistent config is rejected, in `tests/unit/test_schema.py`; guard test that no field name is hard-coded in `src/` or `prompts/` in `tests/unit/test_no_hardcoded_fields.py`
- [X] T085 [US1] Move fixed texts, tap-option titles, list labels, time display format, language and currency markers to `config/messages.yaml` (loaded in `src/lead_capture/conversation/fixed_texts.py`); move remaining eval/sheet tunables to `config/settings.yaml`
- [X] T086 Document every module, class and function with why it exists; enforce with ruff pydocstyle (Google convention) in `pyproject.toml`
- [X] T087 Write `docs/coding-guidelines.md` (no hard-coding, adding a field, interfaces, documentation) and link it from `CLAUDE.md`, the constitution (Principle VII, v1.2.0), the PR template and `README.md`

### Free local model for the first days (2026-09-30): Ollama adapter (research R2, R16)

- [X] T133 [US1] Move vendor-neutral prompt building (signal schema, extraction response schema, turn content, payload parsing) out of `src/lead_capture/adapters/llm/anthropic.py` into `src/lead_capture/adapters/llm/prompting.py`; split the provider-specific output line of `prompts/extraction.md` into `prompts/extraction_output_tool.md` and `prompts/extraction_output_json.md`
- [X] T134 [US1] Contract test `OllamaLLMClient` against the shared LLM suite plus request-shape checks (JSON-schema `format`, models, options, timeout, retries all from settings) with respx in `tests/contract/test_ollama_llm_client.py`
- [X] T135 [US1] Implement `OllamaLLMClient` (Ollama `/api/chat` over httpx, structured output via JSON schema, token counts for usage) in `src/lead_capture/adapters/llm/ollama.py`; add `llm.ollama` group (base URL, models, timeout, concurrency, context size, temperatures, keep-alive) to `config/settings.yaml` and `src/lead_capture/settings.py`; register provider `ollama` in `src/lead_capture/registry.py`; make it the default provider for the first days
- [X] T136 [US1] Let evals run on Ollama: `lead-capture eval --provider ollama` uses Ollama for the bot and the simulated tutee (`evals.ollama_tutee_model`) in `evals/runner.py`, `evals/tutee.py`, `src/lead_capture/cli.py`, with a unit test
- [X] T137 Document the free local setup and the switch back to Claude in `specs/001-whatsapp-lead-capture/quickstart.md`, `research.md` (R2, R16) and `README.md`

### Telegram as a second channel (2026-09-30): FR-031, FR-032, research R17

- [X] T138 Amend `intent.md` (non-goals, §6 `phone`, §10 channels, D12), `spec.md` (FR-031, FR-032), `research.md` (R17), `data-model.md`, `contracts/lead-sheet.md`; add `contracts/telegram-webhook.md`
- [X] T139 [US1] Add field type `phone_number` (normalise to `+<country><number>`) in `src/lead_capture/domain/field_types.py` and `schema.py`; add the `phone` field (`channel_phone: true`), its ask group, the `Leads` "Phone Number" and `Handoffs` "Contact" columns in `config/requirement.yaml`; share-button label in `config/messages.yaml`; unit tests in `tests/unit/test_field_types.py` / `test_schema.py`
- [X] T140 [US1] Extend the channel port: `Capabilities.contact_is_phone` / `can_request_phone`, `InboundMessage.shared_phone` (+ `type=contact`), `OutboundMessage.phone_request_label`; set them in the WhatsApp and fake adapters
- [X] T141 [US1] Engine: pre-fill channel-phone fields when the channel address is a phone number; accept a shared phone as a structured (model-free) input; add the share-phone control when asking a channel-phone field; integration test (Telegram-like fake channel) in `tests/integration/test_phone_capture.py`
- [X] T142 [P] [US1] Contract tests for `TelegramChannel` (shared channel suite + parser, sender, secret-token and retry checks with respx) in `tests/contract/test_telegram_channel.py`
- [X] T143 [US1] Implement `TelegramChannel` (parser, sender, channel, `register_webhook`) in `src/lead_capture/adapters/channels/telegram/`; `channel.telegram` settings, `TELEGRAM_BOT_TOKEN` / `TELEGRAM_WEBHOOK_SECRET` secrets; register provider `telegram` in `registry.py`; silence httpx request logging in `logging.py`
- [X] T144 [US1] CLI `lead-capture set-webhook <public-url>` in `src/lead_capture/cli.py` with a unit test
- [X] T145 Regenerate the sheet template; document Telegram setup in `quickstart.md`, `README.md` and `.env.example`

### Review follow-up (2026-09-30): one-word answers

- [X] T146 [US1] Tell the extraction model which fields the last question asked for (`TurnContext.asked`, prompt rule); when the model finds nothing in a short reply (≤ `conversation.short_answer_max_words`), offer it to the asked fields — fixed-value fields only on an exact valid value, free text only when it is the single text field asked; integration tests in `tests/integration/test_short_answers.py`
- [X] T147 [US1] FR-033: `channel_name: true` on `contact_name` — pre-filled from the chat app's profile name instead of asked; summary shows "Contact: name, phone"; integration test in `tests/integration/test_profile_name.py`
- [X] T148 [US1] Reply language decided in code from the tutee's own words every turn (Hindi vs English marker counts in `config/messages.yaml`); unclear messages (names, board names, numbers, taps) keep the current language; the model's language signal no longer switches it; tests in `tests/unit/test_fixed_texts.py` and `tests/integration/test_reply_language.py`
- [X] T149 [US1] Commit before every model call so SQLite's write lock is never held while a (slow, local) model thinks — webhooks arriving mid-turn failed with "database is locked"; test with a file database in `tests/integration/test_db_not_locked_during_model_calls.py`

**Checkpoint**: MVP — a real WhatsApp chat produces a correct `NEW` row; US1 tests and evals pass

---

## Phase 4: User Story 2 — Tutee drops off and comes back later (Priority: P2)

**Goal**: resume from captured details, stalled marking, several students per number, no duplicate active leads

**Independent Test**: stop half-way, resume later, confirm → one lead with details from both halves; second child from same number → second lead (quickstart scenarios 4–5)

### Tests for User Story 2

- [ ] T088 [P] [US2] Integration test: resume after 2 days → recap of known details, only remaining fields asked; no lead until confirmation, in `tests/integration/test_us2_resume.py`
- [ ] T089 [P] [US2] Integration test: no reply for `conversation.stalled_after_hours` → `stalled`, nothing in the sheet; tutee writes again → `in_progress`, in `tests/integration/test_us2_stalled.py`
- [ ] T090 [P] [US2] Integration test: "I also need a tutor for my daughter" after a completed lead → new conversation and second lead; describing the same student again → existing lead recognised, no duplicate, in `tests/integration/test_us2_multiple_students.py`
- [ ] T091 [P] [US2] Unit test for the window guard (FR-022): a tutee returning after more than 24 hours reopens the window and gets normal replies; any send attempted when `last_inbound_at` is older than `capabilities.window_hours` is dropped and logged as `send_outside_window` (IDs only) and never sent; the engine has no code path that sends a template or starts a conversation, in `tests/unit/test_service_window.py`

### Implementation for User Story 2

- [ ] T092 [US2] Implement `student_key` normalisation and active-conversation lookup per (`contact_id`, `student_key`); handle `new_student` signal by opening a new conversation, in `src/lead_capture/conversation/students.py`
- [ ] T093 [US2] Add `RECAP_AND_CONTINUE` instruction and recap fixed text; engine resumes `stalled` conversations, in `src/lead_capture/conversation/planner.py` and `src/lead_capture/conversation/fixed_texts.py`
- [ ] T094 [US2] Implement the window guard before every send using `MessagingChannel.capabilities.window_hours` and `last_inbound_at`: inside the window send normally; outside it drop the send and log `send_outside_window` (IDs only), in `src/lead_capture/conversation/engine.py`
- [ ] T095 [US2] Implement stalled job (every `jobs.stalled_every_minutes`) and register it, in `src/lead_capture/jobs/stalled.py` and `src/lead_capture/jobs/scheduler.py`
- [ ] T096 [P] [US2] Write eval scenarios `evals/scenarios/us2_*.yaml`: drop-off and resume, two children from one parent, repeated request for the same child

**Checkpoint**: US1 and US2 work independently

---

## Phase 5: User Story 3 — Requests outside what the business serves (Priority: P3)

**Goal**: out-of-area home requests offered online, unsupported languages, not interested / STOP

**Independent Test**: Pune home request accepting and declining online, Tamil opener, "not interested" (quickstart scenarios 6–7)

### Tests for User Story 3

- [ ] T097 [P] [US3] Integration test: home tuition in Pune → offer online; accept → lead with mode `online`; decline → `closed` with `close_reason = out_of_area`, no lead, in `tests/integration/test_us3_out_of_area.py`
- [ ] T098 [P] [US3] Integration test: mode `either` outside NCR → recorded as `online`; PIN code outside NCR ranges with mode ≠ `online` → out-of-area flow, in `tests/integration/test_us3_either_pincode.py`
- [ ] T099 [P] [US3] Integration test: unsupported language → fixed English + Hindi message; "not interested" / "STOP" → acknowledgement, `closed` (`not_interested` / `opted_out`), no further messages, in `tests/integration/test_us3_language_optout.py`

### Implementation for User Story 3

- [ ] T100 [US3] Implement `OFFER_ONLINE_OUT_OF_AREA` flow and `accepts_online` handling in `src/lead_capture/conversation/planner.py` and `src/lead_capture/conversation/engine.py`
- [ ] T101 [P] [US3] Implement `LANGUAGE_UNSUPPORTED` fixed text (both languages) and `other` language handling in `src/lead_capture/conversation/fixed_texts.py`
- [ ] T102 [US3] Implement close transitions with `close_reason` (`not_interested`, `opted_out`, `out_of_area`) and suppression of further sends, in `src/lead_capture/conversation/states.py`
- [ ] T103 [P] [US3] Write eval scenarios `evals/scenarios/us3_*.yaml`: Pune home → accepts online, Pune home → declines, Tamil opener (fixed line), "not interested", "STOP" (fixed line)

**Checkpoint**: US1–US3 work independently

---

## Phase 6: User Story 4 — Tutee reaches a person (Priority: P4)

**Goal**: handoff on request, repeated misunderstanding or complaint; bot silent; ops sees it in the `Handoffs` tab

**Independent Test**: "can I talk to someone?" → handover message, `Handoffs` row, no further bot replies (quickstart scenario 8)

### Tests for User Story 4

- [ ] T104 [P] [US4] Integration test: handoff on request, after `conversation.misunderstand_handoff_threshold` consecutive misunderstandings, and on complaint/sensitive signal → `handed_over`, one `Handoffs` row, no automated replies afterwards; acknowledgement says "after 10 AM" outside ops hours; the row's Reply By = tutee's last message + 24 h and moves forward when the tutee writes again during the handoff, in `tests/integration/test_us4_handoff.py`
- [ ] T105 [P] [US4] Integration test: echoes from the Business app stored as `direction = echo` and never trigger a bot turn; row marked `Resolved` or `conversation.handoff_expiry_hours` elapsed → bot resumes, in `tests/integration/test_us4_resolution.py`
- [ ] T106 [P] [US4] Extend `lead_repository_suite` and Google Sheet contract test for `append_handoff` (A–H incl. Reply By = last inbound + 24 h), `update_handoff_reply_by` (column H only), `resolved_handoffs` (column I = `Resolved`) in `tests/contract/lead_repository_suite.py` and `tests/contract/test_google_sheet_repository.py`

### Implementation for User Story 4

- [ ] T107 [US4] Implement handoff triggers, `misunderstand_streak` tracking, `HANDOFF_ACK(when)` text, `handed_over` state and Reply By updates (`update_handoff_reply_by`) on new tutee messages during a handoff in `src/lead_capture/conversation/handoff.py` and `src/lead_capture/conversation/states.py`
- [ ] T108 [US4] Implement `Handoffs` tab methods in `src/lead_capture/adapters/leads/google_sheet.py` and `src/lead_capture/adapters/leads/in_memory.py`
- [ ] T109 [US4] Implement handoff sync job (every `jobs.handoff_sync_every_minutes`, plus expiry) and register it, in `src/lead_capture/jobs/handoffs.py` and `src/lead_capture/jobs/scheduler.py`
- [ ] T110 [P] [US4] Write eval scenarios `evals/scenarios/us4_*.yaml`: explicit request, repeated nonsense, complaint

**Checkpoint**: US1–US4 work independently

---

## Phase 7: User Story 5 — Consent, privacy and data retention (Priority: P5)

**Goal**: consent before collection, deletion on request, automatic retention

**Independent Test**: decline consent → nothing stored beyond the refusal; deletion request → all data removed; time advanced past retention → rows deleted (quickstart scenarios 9–10)

### Tests for User Story 5

- [ ] T111 [P] [US5] Integration test: consent declined → `closed` (`declined_consent`), no requirement fields stored, no lead; consent message mentions retention periods from settings, in `tests/integration/test_us5_consent.py`
- [ ] T112 [P] [US5] Integration test: "please delete my data" → contact's conversations, messages, outbox rows and sheet rows (via `LeadRepository.delete_lead`) removed, confirmation sent, in `tests/integration/test_us5_deletion.py`
- [ ] T113 [P] [US5] Integration test with frozen clock: messages older than `retention.transcript_days`, leads and conversations older than `retention.lead_days` (local store and sheet), handoff rows older than `retention.handoff_days`, orphan contacts — deleted; newer rows kept, in `tests/integration/test_us5_retention.py`

### Implementation for User Story 5

- [ ] T114 [US5] Implement `awaiting_consent` gate (no extraction or storage of fields before consent; consent via choices or text) in `src/lead_capture/conversation/engine.py` and `src/lead_capture/conversation/states.py`
- [ ] T115 [US5] Implement deletion-request handling in `src/lead_capture/conversation/privacy.py`
- [ ] T116 [US5] Implement retention job on `jobs.retention_cron` and register it; expose as `lead-capture jobs retention`, in `src/lead_capture/jobs/retention.py`, `src/lead_capture/jobs/scheduler.py` and `src/lead_capture/cli.py`
- [ ] T117 [P] [US5] Write eval scenarios `evals/scenarios/us5_*.yaml`: declines consent, asks for deletion after confirming

**Checkpoint**: all five user stories work independently

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: edge cases, costs, load testing, deployment, release checks

- [ ] T118 [P] Integration test then implementation: non-text messages (voice note, image, sticker, document) → `ASK_FOR_TEXT` fixed text (FR-028), in `tests/integration/test_non_text.py` and `src/lead_capture/conversation/fixed_texts.py`
- [ ] T119 [P] Integration test: contradictory later value replaces earlier; unknown board/class → clarifying question, in `tests/integration/test_edge_cases.py`
- [ ] T120 [P] Create `config/rates.yaml` (WhatsApp per-message rates by category incl. 1,000 free service messages/month and 18% GST; Anthropic per-million-token rates for Sonnet 5.5 and Haiku 4.5 incl. cache read/write) from research.md R15
- [ ] T121 Write tests then implement `lead-capture costs --month YYYY-MM` summarising messages and tokens per conversation and per lead from `UsageEvent` and `config/rates.yaml`, in `tests/unit/test_costs.py`, `src/lead_capture/costs/report.py` and `src/lead_capture/cli.py`
- [ ] T122 [P] Implement `StubLLMClient` (random delay from settings, canned valid results, passes `llm_client_suite`) in `src/lead_capture/adapters/llm/stub.py`
- [ ] T123 [P] Implement signed webhook payload builder for load tests in `load/signing.py`
- [ ] T124 Implement Locust profiles `capacity`, `burst`, `soak` (parameters from `load.*` settings; simulated tutee drives full conversations; reconciliation of confirmed leads vs sheet rows; report with latency percentiles, errors, effective settings and cost to `load/reports/<timestamp>.md`) in `load/locustfile.py`, and wire `lead-capture load --profile` in `src/lead_capture/cli.py`
- [ ] T125 [P] Add remaining eval scenarios (voice note placeholder, burst of quick messages, replayed duplicate) and set `evals.pr_subset` to 8 key scenarios in `evals/scenarios/` and `config/settings.yaml`
- [ ] T126 [P] Create `Dockerfile` (python 3.12 slim, uv, non-root user, `data/` volume, `alembic upgrade head` then uvicorn) and `docker-compose.yml` for local runs
- [ ] T127 [P] Write deployment notes (HTTPS via Caddy, Meta webhook setup, coexistence onboarding check, service-account sharing, INR billing before 31 Dec 2026) in `docs/deploy.md`
- [ ] T128 [P] Update `README.md` and `CLAUDE.md` commands if any changed during build
- [ ] T129 Architecture audit test in `tests/unit/test_architecture.py`: no module outside `src/lead_capture/adapters/` imports `anthropic`, `google`, `httpx` Sheets/WhatsApp URLs; no numeric performance/cost literals outside `config/settings.yaml`; no requirement field name from `config/requirement.yaml` appears as a string literal in `src/` or `prompts/` (docs/coding-guidelines.md §1)
- [ ] T130 Audit logs for personal data by running the full test suite with a log-capturing fixture that fails on phone numbers, names or message bodies, in `tests/integration/test_no_pii_in_logs.py`
- [ ] T131 Run quickstart.md validation scenarios 1–13 against a test WhatsApp number and test sheet; record results in `specs/001-whatsapp-lead-capture/checklists/release.md`
- [ ] T132 Run full eval suite and `capacity`, `burst`, `soak` load profiles; attach reports and confirm SC-001–SC-008 thresholds in `specs/001-whatsapp-lead-capture/checklists/release.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → user stories.
- **US1 (Phase 3)** depends only on Foundational. It is the MVP.
- **US2–US5 (Phases 4–7)** depend on Foundational and on the US1 engine, channel and repository (T057–T075). After US1 they are independent of each other and can proceed in parallel or in priority order.
- **Polish (Phase 8)** after the stories it touches; T131–T132 last (release gate).

### Within each phase

- Tests before implementation (they must fail first).
- Ports → adapters → engine → jobs → CLI → evals.
- Settings keys are added to `config/settings.yaml` in the same task that introduces a new tunable.

### Story completion order

```text
Setup → Foundational → US1 (MVP) ─┬─ US2
                                  ├─ US3
                                  ├─ US4
                                  └─ US5  → Polish → Release checks
```

## Parallel Examples

### Foundational

```text
T014 ports/llm.py  |  T015 ports/channel.py  |  T016 ports/leads.py  |  T017 queue/lock/clock ports
T018–T021 contract suites (after the matching port)
T022–T025 fake adapters (after the matching suite)
T026 lists.yaml  |  T030 ids  |  T031 hours  |  T037 logging  |  T040 prompt
```

### User Story 1

```text
Tests:  T041 | T042 | T043 | T044 | T045 | T046 | T047 | T048   (then T049–T056)
Impl:   T057 | T058 | T059 | T063 | T064 | T065 | T066 | T067 | T073   (then T060–T062, T068–T075)
Evals:  T080, T081, T082 in parallel with T077–T079
```

### After US1

```text
US2 (T088–T096) | US3 (T097–T103) | US4 (T104–T110) | US5 (T111–T117)
```

## Implementation Strategy

### MVP first

1. Phases 1–2 (Setup, Foundational).
2. Phase 3 (US1) → **stop and validate**: quickstart scenarios 1–3, US1 evals, a real test chat on WhatsApp.
3. Demo to the operations team with the real sheet.

### Incremental delivery

- Add US2 → validate → demo; then US3, US4, US5 in priority order (or in parallel after US1).
- Each story ends with its tests, evals and checkpoint passing.
- Polish and release checks (T131–T132) gate the first production deploy.

### Commit and PR convention

- One PR per story phase (or smaller), branch `001-whatsapp-lead-capture`.
- Commit prefixes: `test:` for failing tests, `feat(Gx):` for implementation (G1–G7 from intent.md), `eval:` for eval scenarios and runner, `fix(Gx):` for fixes.
- Tick tasks in this file in the same commit that completes them.

## Notes

- `[P]` tasks touch different files and have no unfinished dependency.
- Every new tunable number goes into `config/settings.yaml` with a validated default (Principle VI).
- No vendor SDK imports outside `src/lead_capture/adapters/` (checked by T129).
- Stop at any checkpoint to validate the story on its own.
