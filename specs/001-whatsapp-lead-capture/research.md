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
  ~60 words (regenerate once, then fall back to a fixed text); reject any
  reply containing a currency amount the tutee did not state (FR-006).
- **Cost-saving defaults** (details and config keys in R16): turns that code
  can answer on its own (button taps, greeting and consent, summary, closing)
  use fixed English/Hindi texts with no model call; each call gets the
  validated state plus only the last few messages; extraction runs on a
  smaller model. All three are configuration switches.
- **Provider independence**: the engine calls an `LLMClient` interface, not
  the Anthropic SDK directly (R16), so another model or provider can be
  swapped in via configuration.
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
  - Conversations are tutee-initiated only: the bot replies within the
    24-hour window and never sends templates or business-initiated messages
    (FR-022); a send that would fall outside the window is dropped and logged.
- **Rationale**: Official, no third-party BSP fee required, supports
  interactive messages.
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

- **Decision**: Process one conversation at a time per WhatsApp number, with a
  2-second debounce so several quick messages are answered as one turn. Both
  sit behind a `ConversationLock` interface, and inbound turns flow through a
  `TurnQueue` interface; v1 implements both in-process (asyncio), so a
  Redis/SQS queue and a shared lock can replace them later (see R14).
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
  - **Eval suite** (`evals/`) with a **simulated tutee**. Each scenario in
    `evals/scenarios/*.yaml` defines an opening message, the tutee's true facts
    (`tutee_facts`), a style (English / Hindi / Hinglish, short replies,
    typos…) and the expected outcome. A small, cheap Claude model
    (`EVAL_TUTEE_MODEL`, e.g. `claude-haiku-4-5`) plays the tutee and answers
    the bot's questions **only from those facts**, in that style. The real
    conversation engine and model run against it, with fake WhatsApp and an
    in-memory sheet.
  - Each scenario runs several times (default 3) because replies vary. Checks
    are deterministic and mapped to the spec:
    recorded lead equals `tutee_facts` field by field (SC-001); assistant
    messages ≤ 8 (SC-002); no field asked twice and no amount suggested
    (SC-003); ≤ 2 questions and matching language per message (FR-001/002);
    expected outcome — lead recorded, closed out-of-area, handed over
    (user stories). An optional model-graded "sounds human" score is reported
    but not gating.
  - A few scenarios keep **fixed tutee lines** where exact wording matters
    (a voice-note placeholder, "STOP", a Tamil opener, a replayed duplicate).
  - CI (GitHub Actions): lint + tests on every PR; evals on PRs touching
    `src/lead_capture/conversation/`, `prompts/` or `evals/`, with a pass-rate
    threshold of 95% per check.
- **Rationale**: Constitution Principle III. A simulated tutee avoids brittle
  scripts (the bot won't always ask in the same order) and lets the eval
  compare the recorded lead exactly against known facts.
- **Alternatives considered**: fully scripted tutee lines (break whenever the
  question order changes); manual QA transcripts only (not repeatable);
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

## R13. Load and performance testing

- **Decision**: [Locust](https://locust.io/) load scenarios in `load/`, run via
  `lead-capture load --profile <name>` in the Verify stage before each release
  (not on every PR). The load generator sends correctly signed webhook
  payloads, and a simulated-tutee driver answers the bot's replies so full
  conversations complete.

  | Profile | Setup | Load | Pass criteria |
  |---|---|---|---|
  | `capacity` | Claude replaced by a stub with 1–3 s random delay; fake WhatsApp; in-memory sheet | ramp to 100 concurrent tutees | webhook ack p99 < 1 s; 0 errors; 0 lost or duplicate messages |
  | `burst` | real Claude API; fake WhatsApp; a **test** Google Sheet | 30 tutees start within 60 s and complete full chats; peaks of 5 inbound msg/s for 10 min | reply p95 < 5 s (SC-005); every confirmed lead in the sheet exactly once within 10 s (SC-006, SC-007); outbox back to 0 |
  | `soak` | stubbed Claude; fake WhatsApp; in-memory sheet | steady 1 msg/s for 3 hours | memory stable (< 10% growth after warm-up); scheduled jobs keep running; no latency drift |

  Results (latency percentiles, error counts, lead reconciliation) are saved
  to `load/reports/<timestamp>.md`.
- **Assumed peak** (no figure given yet): 30 tutees chatting at the same time
  and 5 inbound messages per second for 10 minutes, e.g. right after an ad
  goes live. Raise the `burst` profile when real traffic data exists.
- **Rationale**: the spec sets latency and exactly-once targets that only
  hold if they are measured under bursty traffic; the biggest risks (Claude
  latency and rate limits, SQLite write serialisation, Sheets quota, the single
  process) only show up under load.
- **Alternatives considered**: k6 (excellent, but JavaScript — Locust keeps the
  whole toolchain in Python and can reuse the eval tutee simulator); running
  load tests on every PR (too slow and, with the real model, costly).

## R14. Scaling path

v1 is deliberately one process. These are the steps, in the order they are
likely to be needed, and what triggers each.

| Step | Trigger | Change |
|---|---|---|
| 1. Tune the model calls | `burst` reply p95 > 5 s, or Claude 429s | higher Anthropic usage tier; prompt caching; smaller model for extraction; optionally merge extraction + reply into one call; cap concurrent model calls |
| 2. Move leads off the Sheet | > ~30k lead rows, several ops users editing at once, or Sheets 429s | new `LeadRepository` implementation for PostgreSQL and/or a CRM (Zoho, HubSpot, Salesforce); the Sheet becomes a read-only export |
| 3. PostgreSQL for the bot store | before running more than one instance | change `DATABASE_URL`; Alembic migrations already apply |
| 4. Scale out | one instance can't keep reply p95 < 5 s | stateless webhook receivers → queue partitioned by WhatsApp number (Redis Streams, SQS FIFO or Cloud Tasks) → autoscaled conversation workers; scheduled jobs in one dedicated worker or cron via the CLI |
| 5. Operate at scale | multiple numbers, cities or brands; high volume | tenant ID across tables and lists; metrics and alerts (reply latency, queue depth, outbox backlog, model errors, cost per lead); fallback route to Claude (e.g. AWS Bedrock or Google Vertex AI) |

**Seams built in v1 so these steps stay small:**

- `LeadRepository` — sheet today, database or CRM later (step 2).
- SQLAlchemy + Alembic — SQLite today, PostgreSQL later (step 3).
- `TurnQueue` interface — incoming turns go through it; v1 uses an in-process
  asyncio implementation, later a Redis/SQS one (step 4).
- `ConversationLock` interface — per-number lock and debounce; v1 in-memory,
  later a PostgreSQL advisory lock or queue partitioning (step 4).
- Idempotency on WhatsApp message ID and Lead ID, and the lead outbox — make
  retries and multiple workers safe (step 4).
- Every scheduled job is also a CLI command — can move to cron or a single
  worker without code changes (step 4).
- The model name is configuration — per-call model choice without code changes (step 1).


## R15. Running costs

All figures are **estimates as of 29 Sep 2026**, to be replaced with measured
numbers once the service logs messages and tokens per conversation (see
"Tracking" below). Currency conversion assumes **₹88 = US$1**.

### Assumptions used throughout

| Assumption | Value | Source |
|---|---|---|
| Bot messages per conversation (average across completed and abandoned) | 8 | spec SC-002 target (≤ 8 for completed leads) |
| Conversations that become leads | 60% | spec SC-004 target |
| Tutee turns (model calls ×2) per conversation | ~9 completed, ~4 abandoned | plan: one extraction + one reply call per turn |
| Templates sent by the bot | none | all conversations are tutee-initiated (FR-022) |
| Volumes modelled | 50 / 150 / 300 conversations per day | plan scale (a few hundred per day) |

### 1. WhatsApp Business Platform (Meta)

This app sends **no templates** (FR-022), so only the first row applies; the
template rows are listed for reference.

Meta charges **per delivered message** from the business, by message type and
the recipient's country. Messages from tutees are always free. The Cloud API
itself (hosting, number registration, business verification) has no fee, and
using it directly avoids the ₹0.08–₹0.30 per-message markup that resellers
(BSPs) add.

| Message the bot sends | Until 30 Sep 2026 | From **1 Oct 2026** (India) |
|---|---|---|
| Reply within 24 h of the tutee's last message ("service" — every normal bot and human reply) | free | **1,000 free per phone number per month**, then ≈ ₹0.115 each |
| Utility template (e.g. request received), inside the 24-hour window | free | charged, ≈ ₹0.115 |
| Utility template outside the 24-hour window | ≈ ₹0.115 | ≈ ₹0.115 |
| Authentication template | ≈ ₹0.115 | ≈ ₹0.115 |
| Marketing template | ≈ ₹0.86 (raised from ≈ ₹0.78 in 2026) | ≈ ₹0.86 |
| Anything within 72 h of a tutee arriving from a click-to-WhatsApp ad or Facebook CTA | free | **still free** |

- **GST of 18%** applies on top of Meta's charges.
- Replies written by an AI bot are billed the same as human replies — there is no separate AI category.
- Replies ops staff send from the WhatsApp Business app (coexistence, R4) are billed the same as bot replies.
- Button and list (interactive) messages count as one message each.
- **Billing currency:** India accounts must move to INR billing by **31 Dec 2026**; from 1 Jan 2027 non-INR accounts stop delivering messages.
- **Uncertainty:** the 1 Oct 2026 India rate and the 1,000-message allowance come from Indian provider blogs; at least one source reports no free allowance. Confirm in WhatsApp Manager → Billing / Meta's rate card before budgeting.

**Estimated monthly WhatsApp cost (from 1 Oct 2026, incl. GST):**

| Volume | Bot messages / month | Billable (after 1,000 free) | Monthly | Per completed lead |
|---|---|---|---|---|
| 50 conversations/day | ~12,000 | ~11,000 | **~₹1,500** | ~₹1.70 |
| 150 conversations/day | ~36,000 | ~35,000 | **~₹4,750** | ~₹1.75 |
| 300 conversations/day | ~72,000 | ~71,000 | **~₹9,600** | ~₹1.80 |

If most tutees arrive through click-to-WhatsApp ads, most of these
conversations fall inside the free 72-hour window and cost close to nothing.

### 2. Claude API (Anthropic)

Official list prices (per million tokens):

| Model | Input | Output | Cache write (5 min) | Cache read |
|---|---|---|---|---|
| Claude Sonnet 5.5 (`claude-sonnet-5-5`, default) | $2 | $10 | $2.50 | $0.20 |
| Claude Haiku 4.5 | $1 | $5 | $1.25 | $0.10 |

**Per tutee turn** (two calls, system prompt and tool schema cached):

| Call | Cached input | Other input | Output |
|---|---|---|---|
| Extraction | ~2,000 | ~1,800 (transcript, state) | ~150 |
| Reply | ~1,500 | ~1,800 | ~80 |

≈ **US$0.010 per turn** with Sonnet 5.5 for both calls (≈ $0.0055 extraction +
$0.0047 reply), plus ~10% for guard-triggered regenerations and retries. That
gives ≈ $0.10 (₹8.8) per completed conversation, ≈ $0.045 per abandoned one,
and ≈ $0.078 (₹6.9) per conversation on average.

**Estimated monthly Claude cost:**

| Volume | Sonnet for both calls | Haiku for extraction, Sonnet for replies (≈ −26%) | Haiku for both (≈ −50%) |
|---|---|---|---|
| 50 conversations/day | **~₹10,300** | ~₹7,600 | ~₹5,200 |
| 150 conversations/day | **~₹30,900** | ~₹22,900 | ~₹15,500 |
| 300 conversations/day | **~₹61,800** | ~₹45,700 | ~₹30,900 |

- Per completed lead: ≈ ₹11.5 with Sonnet for both calls.
- Indian GST may apply to the Anthropic invoice depending on billing setup; check the invoice.
- Moving extraction to Haiku is the first cost lever and is a configuration change (R2, R14 step 1); it should only be made if evals still pass.

**Development and testing:**

| Activity | Estimate |
|---|---|
| Full eval run (≈ 30 scenarios × 3 runs, Sonnet bot + Haiku simulated tutee) | ≈ $10–12 per run |
| CI evals | only on PRs touching conversation code, prompts or evals |
| `burst` load test (30 full conversations, real model) | ≈ $3–4 per run |
| `capacity` and `soak` load tests | ≈ $0 (model stubbed) |

### 3. Hosting and other services

| Item | Estimate |
|---|---|
| Small Linux VM (1 vCPU, 1 GB) with persistent disk | ≈ US$6–12/month (≈ ₹500–1,000) |
| HTTPS certificate | free (Let's Encrypt via Caddy) |
| Google Sheets API and service account | free |
| Business phone number for WhatsApp | an existing or new SIM/landline not already on WhatsApp; no Meta fee |
| Backups (SQLite file copy to object storage) | < US$1/month |

### 4. Total monthly estimate

| Volume | WhatsApp | Claude (Sonnet ×2) | Hosting | **Total / month** | **Per completed lead** |
|---|---|---|---|---|---|
| 50 conversations/day (~900 leads) | ~₹1,500 | ~₹10,300 | ~₹800 | **~₹12,600** | **~₹14** |
| 150 conversations/day (~2,700 leads) | ~₹4,750 | ~₹30,900 | ~₹800 | **~₹36,500** | **~₹13.5** |
| 300 conversations/day (~5,400 leads) | ~₹9,600 | ~₹61,800 | ~₹1,000 | **~₹72,400** | **~₹13.4** |

The language model is about 80–85% of running cost; WhatsApp about 13%.

### Cost levers, in order of impact

1. **Model choice per call** — Haiku for extraction (−26% of model cost), then test Haiku for replies too (−50%).
2. **Fewer bot messages per conversation** — lowers both WhatsApp and model cost; the "≤ 8 messages" target (SC-002) is also a cost target. Never split one reply into several messages.
3. **Click-to-WhatsApp ads** as the entry point — conversations inside the 72-hour free window have no WhatsApp charge.
4. **Shorter context** — cap transcript sent to the model (`llm.context_messages`, default 6) and keep the system prompt cached.
5. **No templates** — the design sends none (FR-022). If reminders were ever added, they would need a spec change and would cost ≈ ₹0.115 (utility) to ≈ ₹0.86 (marketing) each.

### Tracking

- Log per conversation (IDs only, no personal data): bot messages sent, model calls, input/output/cached tokens per model.
- `/healthz` stays personal-data-free; a `lead-capture costs --month YYYY-MM` CLI command summarises messages, tokens and estimated cost per conversation and per lead, using rates from configuration (`config/rates.yaml`) so they can be updated when Meta or Anthropic change prices.
- Eval and load-test reports include token usage and estimated cost per run.

### After the R16 optimisations

With the default optimisations 1–3 in R16 (no model call on deterministic
turns, trimmed context, Haiku for extraction), model cost falls by ≈ 70%:
≈ ₹2.5 per completed conversation, ≈ ₹3.3 per lead, ≈ ₹9,000/month at 150
conversations a day. Total cost per completed lead, WhatsApp and hosting
included, falls from ≈ ₹13.5 to **≈ ₹5**. These remain estimates until
measured with `lead-capture costs`.

### Sources

- Meta — Pricing on the WhatsApp Business Platform: https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing
- MyOperator — WhatsApp Business API pricing in India 2026: https://myoperator.com/blog/whatsapp-business-api-pricing-india-2026
- Mark360.ai — WhatsApp service message pricing India (1 Oct 2026): https://mark360.ai/blog/whatsapp-service-message-pricing-october-1-2026
- Wati — WhatsApp service message pricing changes (2026): https://www.wati.io/en/blog/whatsapp-service-message-pricing/
- SendPulse — WhatsApp service message pricing changes, Oct 2026: https://sendpulse.com/blog/whatsapp-service-message-pricing
- Anthropic — Claude pricing: https://platform.claude.com/docs/en/about-claude/pricing

## R16. Swappable services and configurable parameters

Implements constitution Principle VI for this feature. Goal: changing the
language model, the messaging app, the lead store, or any performance/cost
setting is a configuration change or a new adapter — never an edit to the
conversation engine.

### Interfaces (ports) and adapters

| Interface | Responsibility | v1 adapter | Test adapter | Later options |
|---|---|---|---|---|
| `LLMClient` | `extract(turn) -> ExtractionResult`; `write_reply(turn, instruction) -> str`; reports token usage | `AnthropicLLMClient` | `FakeLLMClient` (scripted), `StubLLMClient` (delay only, for load tests) | Claude via AWS Bedrock / Google Vertex; another provider |
| `MessagingChannel` | parse and verify inbound webhooks into normalised `InboundMessage`s; `send_text`, `send_choices` (buttons/list); declares `capabilities` (max buttons, template rules, service window) | `WhatsAppCloudChannel` | `FakeChannel` | Telegram, Instagram DM, web chat, SMS; a WhatsApp BSP |
| `LeadRepository` | append/find/delete leads, handoff rows, lists sync (contract in `contracts/lead-sheet.md`) | `GoogleSheetLeadRepository` | `InMemoryLeadRepository` | PostgreSQL, Zoho / HubSpot / Salesforce CRM |
| `TurnQueue` | deliver turns in order per contact | in-process asyncio | same | Redis Streams, SQS FIFO, Cloud Tasks |
| `ConversationLock` | one turn at a time per contact | in-memory | same | PostgreSQL advisory lock, Redis |
| `Clock` | current time in the configured time zone | system clock | frozen clock | — |

Rules:

- The conversation engine, planner, guards and domain code import only these
  interfaces and the normalised types (`InboundMessage`, `OutboundMessage`,
  `Choice`, `ExtractionResult`, `TokenUsage`). No vendor SDK imports outside
  `adapters/`.
- The engine asks the channel what it can do (`capabilities`) instead of
  assuming WhatsApp — e.g. a channel without buttons gets numbered options, and the
  engine reads the reply window length from `capabilities.window_hours`.
- Adapters are chosen by name in `config/settings.yaml`
  (`llm.provider`, `channel.provider`, `leads.repository`, …) through a small
  registry; secrets stay in environment variables.
- Webhooks are mounted per channel at `/webhooks/{channel}` so a second
  channel can run alongside WhatsApp.
- Each adapter passes a shared contract test suite for its interface
  (`tests/contract/`), so a new adapter is accepted when it passes the same
  tests as the old one.

### Configurable parameters

All live in `config/settings.yaml`, validated by a Pydantic settings model at
start-up (the service refuses to start on invalid values). Any key can be
overridden by an environment variable (`LC__LLM__REPLY_MODEL=…`). Eval and
load-test reports print the effective settings.

| Group | Key | Default | Why this default |
|---|---|---|---|
| **LLM** | `llm.provider` | `anthropic` | R2 |
| | `llm.extraction_model` | `claude-haiku-4-5` | structured extraction works well on a small model; ≈ −25% cost (R15) |
| | `llm.reply_model` | `claude-sonnet-5-5` | replies are what tutees judge |
| | `llm.combined_call` | `false` | one call per turn saves ≈ 35% but writes the reply before validation — experiment only |
| | `llm.context_messages` | `6` | state carries the facts; ≈ −35–40% input tokens vs 20 |
| | `llm.max_output_tokens.extraction` / `.reply` | `400` / `200` | bounded cost and latency |
| | `llm.temperature.extraction` / `.reply` | `0` / `0.7` | deterministic extraction, natural replies |
| | `llm.prompt_cache` | `true` | system prompt and tool schema cached |
| | `llm.timeout_seconds` | `8` | caps a stuck call; typical calls finish in 1–3 s, so the 5 s p95 target is unaffected |
| | `llm.max_retries` | `2` | with exponential backoff |
| | `llm.max_concurrent_calls` | `20` | protects rate limits during bursts |
| | `llm.skip_for_deterministic_turns` | `true` | button taps, greeting/consent, summary, closing use fixed texts; ≈ −30–35% calls |
| | `llm.max_regenerations` | `1` | then fall back to the fixed text for that instruction |
| **Conversation** | `conversation.max_questions_per_message` | `2` | FR-001 |
| | `conversation.max_words_per_message` | `60` | FR-001 |
| | `conversation.debounce_ms` | `2000` | R8 |
| | `conversation.misunderstand_handoff_threshold` | `3` | FR-023 |
| | `conversation.stalled_after_hours` | `24` | FR-019 |
| | `conversation.handoff_expiry_hours` | `72` | R4 |
| **Channel** | `channel.provider` | `whatsapp_cloud` | R3 |
| | `channel.send_timeout_seconds` / `channel.max_retries` | `5` / `3` | contract `whatsapp-webhook.md` |
| **Leads** | `leads.repository` | `google_sheet` | R5 |
| | `leads.outbox_interval_seconds` | `60` | R6/R9 |
| | `leads.max_backoff_seconds` | `300` | R5 |
| **Operations** | `ops.timezone` / `ops.hours_start` / `ops.hours_end` | `Asia/Kolkata` / `10:00` / `17:00` | intent |
| **Retention** | `retention.transcript_days` / `retention.lead_days` / `retention.handoff_days` | `90` / `365` / `90` | intent / FR-026 |
| **Jobs** | `jobs.stalled_every_minutes` / `jobs.handoff_sync_every_minutes` / `jobs.retention_cron` | `15` / `5` / `0 3 * * *` | R9 |
| **Costs** | `costs.rates_file` / `costs.usd_to_inr` | `config/rates.yaml` / `88` | R15 |
| **Evals** | `evals.repeats` / `evals.pass_threshold` / `evals.tutee_model` / `evals.pr_subset` | `3` / `0.95` / `claude-haiku-4-5` / 8 key scenarios, 1 run each | R10; full suite nightly and before release |
| **Load** | `load.burst.concurrent_tutees` / `load.burst.peak_msgs_per_second` / `load.burst.minutes` | `30` / `5` / `10` | R13 |

Business rules that are product decisions (serviceable cities, languages,
required fields, allowed values) stay in `config/lists.yaml` and `intent.md`,
not in this file — changing them needs the approval described in the
constitution.

### Cost optimisations and how they map to settings

| # | Optimisation | Setting | Default | Risk | Estimated effect on model cost |
|---|---|---|---|---|---|
| 1 | No model call on deterministic turns | `llm.skip_for_deterministic_turns` | on | none | −30–35% |
| 2 | Send state + last few messages only | `llm.context_messages` | 6 | low | −35–40% |
| 3 | Smaller model for extraction | `llm.extraction_model` | Haiku 4.5 | low–medium (eval-gated) | −25% |
| 4 | One combined call per turn | `llm.combined_call` | off | medium | −35% more |
| 5 | Smaller model for replies | `llm.reply_model` | Sonnet 5.5 | higher — replies are the product | −50% of reply cost |
| — | Eval subset on PRs, full suite nightly | `evals.pr_subset` | on | none | ≈ −80% eval spend |

Defaults 1–3 together: ≈ −70% model cost (R15). Options 4 and 5 are
experiments: change the setting, run `lead-capture eval` and the `burst` load
profile, and adopt only if every check still passes.

