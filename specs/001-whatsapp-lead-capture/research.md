# Research: WhatsApp Lead Capture

**Feature**: [spec.md](spec.md) · **Date**: 2026-09-29

Each decision below resolves an open technical question from the plan's
Technical Context. Facts about third-party platforms (WhatsApp, Google) should
be re-checked against current documentation during the Build stage.

## R1. Language and web framework

- **Decision**: Python 3.12 with FastAPI (served by Uvicorn).
- **Rationale**: One small webhook service; Python has first-party SDKs for
  Claude (`anthropic`) and Google (`google-api-python-client` / `gspread`),
  Pydantic gives strict validation that maps directly to constitution
  Principle II, and FastAPI's async model lets the webhook return immediately
  while processing continues in the background.
- **Alternatives considered**: Node.js/Express (equally viable; Python chosen
  for Pydantic validation and simpler eval scripting); Laravel/PHP (heavier for
  a single webhook service, weaker LLM SDK support).

## R2. Language model and how it is used

- **Decision**: Claude via the Anthropic API — `claude-sonnet-5-5` by default,
  model name from configuration. The model is used for two jobs per turn:
  1. **Extraction** — a forced tool call (`record_requirements`) that returns
     structured candidate values for any fields found in the tutee's message,
     plus flags (`wants_human`, `not_interested`, `language`, `off_topic`).
  2. **Reply writing** — given the conversation, the validated state and a
     code-computed "what to ask next" instruction, write the next message.
- **Rationale**: Splitting extraction (structured, validated by code) from
  reply writing keeps the model away from data integrity (Principle II) while
  keeping the conversation natural (G1). Code, not the model, decides the stage
  (consent → collecting → confirming → completed) and which fields are missing.
- **Guardrails in code**: reject replies with more than two questions or over
  ~60 words (regenerate once, then fall back to a template phrase); reject any
  reply containing a currency amount the tutee did not state (FR-006).
- **Alternatives considered**: a pure rules/form bot (fails G1 and G3); letting
  the model drive the whole flow and emit the final lead (violates Principle
  II); a cheaper model for extraction only (possible later optimisation, noted
  in plan).

## R3. WhatsApp integration

- **Decision**: WhatsApp Business Platform **Cloud API**, one webhook endpoint.
  - Verify the webhook subscription with `hub.mode` / `hub.verify_token` /
    `hub.challenge`; verify every POST with the `X-Hub-Signature-256` HMAC
    (app secret).
  - Acknowledge with HTTP 200 immediately; process asynchronously.
  - Deduplicate on the WhatsApp message ID (unique constraint).
  - Use interactive **reply buttons** (max 3) for mode, consent and summary
    confirmation, and an interactive **list** for board; always accept typed
    text too (FR-004).
  - Outside the 24-hour window, send only approved templates (FR-022).
- **Rationale**: Official, no third-party BSP fee required, supports
  interactive messages and templates.
- **Alternatives considered**: a Business Solution Provider (Wati, Gupshup,
  etc.) — adds cost and a dependency; unofficial WhatsApp Web automation —
  violates WhatsApp terms.

## R4. Human handoff

- **Decision**: Use WhatsApp **coexistence** so the operations team replies
  from the WhatsApp Business app on the same number the bot uses. On handoff
  the bot sets the conversation's handoff flag, stops replying (FR-024) and
  appends a row to a `Handoffs` tab in the operations sheet (time, WhatsApp
  number, name, reason, captured-so-far summary). Messages the team sends from
  the app arrive as message echoes and are stored in the transcript; the bot
  stays silent while the flag is set. The team clears the flag by marking the
  row "Resolved" (read by a periodic sync) — or it expires after 72 hours.
- **Rationale**: Matches the spec assumption (same number, ops team, same
  hours) with no inbox software to build; the sheet is already where the team
  works.
- **Alternatives considered**: a separate agent number (confusing for tutees);
  a shared inbox product (cost; can be adopted later); email alerts only (easy
  to miss).
- **Check during build**: coexistence onboarding requirements for the chosen
  number and whether echo webhooks are enabled for it.

## R5. Operational DB access (Google Sheet)

- **Decision**: Google Sheets API v4 through a service account that is shared
  as editor on that single sheet only. All access sits behind a
  `LeadRepository` interface with a `GoogleSheetLeadRepository`
  implementation (plus an in-memory implementation for tests).
  - Append with `values.append` (`INSERT_ROWS`, `USER_ENTERED`) writing only
    columns A–Z; never write AA–AC.
  - Before appending, search column A for the Lead ID (idempotency).
  - Handle 429/5xx with exponential backoff and jitter.
- **Rationale**: Direct fit with intent §9 and constitution Principle II;
  the per-project quota (hundreds of requests per minute) is far above
  expected lead volume.
- **Alternatives considered**: Apps Script web app as a write proxy (extra
  moving part, weaker auth); writing CSV to Drive (no concurrent editing).

## R6. Reliability of lead recording — outbox

- **Decision**: On confirmation, the lead is first written to a local
  `lead_outbox` table in the same transaction as the conversation state
  change. A background worker drains the outbox to the sheet, retrying until
  success, and marks each row `synced`. The tutee's confirmation message does
  not wait for the sheet.
- **Rationale**: Guarantees FR-017 / SC-007 (never lost, never duplicated)
  even when Google is briefly unavailable, while keeping reply latency low.
- **Alternatives considered**: synchronous write before replying (a Google
  outage would block tutees); an external queue such as Redis/RabbitMQ
  (unnecessary infrastructure at this scale — Principle V).

## R7. Bot working store

- **Decision**: SQLite (WAL mode) on a persistent volume, accessed through
  SQLAlchemy 2.x with Alembic migrations.
- **Rationale**: Single service, low write volume, zero operational overhead;
  SQLAlchemy keeps a move to PostgreSQL a configuration change if the service
  is ever scaled out.
- **Alternatives considered**: PostgreSQL (better for multiple instances;
  overkill for v1); Redis (state would be lost without careful persistence;
  weaker for transcripts and retention queries).

## R8. Concurrency and message bursts

- **Decision**: Process one conversation at a time per WhatsApp number (an
  in-process per-number lock), with a 2-second debounce so several quick
  messages are answered as one turn.
- **Rationale**: Prevents interleaved replies and double extraction; 2 s keeps
  total reply time within the 5 s target.
- **Alternatives considered**: no debounce (fragmented replies); longer
  debounce (misses latency target).

## R9. Scheduled jobs

- **Decision**: APScheduler inside the service, all times in Asia/Kolkata:
  - every 15 min: mark conversations with no reply for 24 h as `stalled`;
  - every 5 min: sync `Handoffs` tab resolutions;
  - every 1 min (and on demand): drain the lead outbox;
  - daily 03:00: delete messages older than 90 days, and leads / conversation
    records older than 1 year (local store and sheet rows).
- **Rationale**: One deployable unit; jobs are idempotent so a missed run is
  harmless.
- **Alternatives considered**: system cron calling CLI commands (fine too —
  the jobs are also exposed as CLI commands for manual runs).

## R10. Testing and evals

- **Decision**:
  - **pytest** for unit, contract and integration tests; the Claude client,
    WhatsApp sender and sheet repository are replaced by fakes in these.
  - **Eval suite** (`evals/`): scripted tutee conversations in YAML (English,
    Hindi, Hinglish, typos, multi-field messages, corrections, out-of-area,
    budget-unsure, handoff requests, other languages). A runner drives the
    real conversation engine against the real model and scores each run with
    deterministic checks mapped to spec success criteria: required fields
    captured and valid (SC-001), assistant message count (SC-002), no re-asked
    field and no suggested amount (SC-003), handoff honoured (SC-008).
    An optional model-graded "sounds human" score is reported but not gating.
  - CI (GitHub Actions): lint + tests on every PR; evals on PRs touching
    `src/lead_capture/conversation/`, `prompts/` or `evals/`, with a pass-rate
    threshold of 95% per check.
- **Rationale**: Constitution Principle III — deterministic code gets tests;
  non-deterministic conversation gets evals tied to the spec.
- **Alternatives considered**: manual QA transcripts only (not repeatable);
  exact-match snapshot tests of model replies (brittle).

## R11. Deployment

- **Decision**: One Docker image running on a small Linux VM (1 vCPU / 1 GB)
  behind HTTPS (Caddy or the host's reverse proxy), SQLite on a mounted
  volume, secrets via environment variables. Health endpoint for uptime
  monitoring.
- **Rationale**: Webhooks need a stable public HTTPS URL and an always-on
  process for scheduled jobs; a single VM is the simplest fit.
- **Alternatives considered**: serverless (Cloud Run / Lambda) — cold starts
  threaten the 5 s target and scheduled jobs and SQLite need extra services;
  PaaS such as Render/Railway — acceptable alternative if a managed host is
  preferred.

## R12. Allowed values

- **Decision**: Allowed values (class levels, boards, subjects, NCR cities,
  modes, budget units, lead statuses) live in `config/lists.yaml` in the repo
  and are mirrored into the sheet's `Lists` tab by a CLI command. Code reads the
  YAML; the sheet copy exists for ops dropdowns.
- **Rationale**: Reviewed in git (visible stage history), versioned with the
  validator that depends on them.
- **Alternatives considered**: reading lists from the sheet at runtime (ops
  edits could silently break validation).
