# Lead Management System Constitution

These are the standing rules for every feature built in this repository. They
apply to humans and AI coding agents alike. Product intent lives in
[`intent.md`](../../intent.md); this constitution says **how** we build it.

## Core Principles

### I. Intent Is the Source of Truth
Every feature traces back to a goal in `intent.md` (G1–G7). Specs, plans, tasks
and code must not contradict it or build anything listed under its Non-goals.
Changes to required lead fields (intent §6) or the lead lifecycle (intent §8)
require explicit human approval in a PR that updates `intent.md` first.

### II. Validated Data Only (NON-NEGOTIABLE)
The language model handles conversation and extraction; code decides what is
stored. Nothing is written to the operational Google Sheet from raw model
output — only from values validated against the allowed lists and confirmed by
the tutee. All sheet access goes through the `LeadRepository` interface; no
other module calls the Google Sheets API. The bot only appends rows and never
overwrites ops-owned columns.

### III. Test-First, Eval-Backed
Tests are written before implementation and must fail first. Deterministic
code (validation, lifecycle, repository, webhook handling) is covered by unit
and integration tests. Conversation behaviour is covered by **evals**: scripted
tutee chats (English, Hindi, Hinglish, messy input) scored against intent §11 —
all required fields captured, nothing re-asked, no budget ranges quoted,
out-of-area handling, handoff on request. A feature is not done until its
tests and evals pass in CI.

### IV. Privacy and Consent by Default
Consent is captured before any personal data is stored. Collect only what intent
§6 lists. No personal data in logs beyond IDs. Transcripts are deleted after
90 days and leads after 1 year. Secrets and the sheet ID come from
configuration, never from source code. Comply with India's DPDP Act.

### V. Small, Reversible Steps
Work in small tasks that each fit one reviewable pull request. Prefer the
simplest design that satisfies the spec; new dependencies, services or
abstractions need a stated reason in the plan. Idempotency is required
wherever WhatsApp or Google may retry (dedupe on `wa_message_id` and Lead ID).

### VI. Configurable and Swappable by Design
External services and tunable numbers are never hard-wired into business logic.

- **Interfaces for every external service.** Conversation and domain code talk
  only to interfaces, never to a vendor SDK: `LLMClient` (language model),
  `MessagingChannel` (WhatsApp today; others later), `LeadRepository`
  (Google Sheet today; database or CRM later), plus `TurnQueue`,
  `ConversationLock` and `Clock`. Vendor code lives in one adapter module per
  service, selected by configuration. Every interface has a fake/in-memory
  adapter used in tests. Swapping a vendor means adding an adapter and
  changing config — not editing the conversation engine.
- **Performance and cost parameters are configuration, not constants.** Model
  per call, token limits, context size, which turns use the model, timeouts,
  retries, concurrency caps, debounce, thresholds, schedules, retention periods
  and price rates are read from `config/settings.yaml` (overridable by
  environment variables) and validated at start-up. Defaults live in config,
  with the reason for each default in the feature's research notes.
- **Every change to these settings is measurable**: eval and load-test reports
  record the settings used, alongside quality, latency and cost results, so a
  cheaper or faster setting is adopted only when the evals still pass.

## Product Constraints

- Channel: WhatsApp Business Platform (Cloud API). Conversations are started
  by tutees only; the bot replies only within the 24-hour customer-service
  window and sends no business-initiated messages or templates.
- Operational DB (v1): a native Google Sheet on Google Drive, accessed through
  a service account limited to that one sheet.
- Conversation state and transcripts live in the bot's own store, not the sheet.
- Languages: English and Hindi (including Hinglish) only.
- Home tuition: Delhi/NCR only; online tuition has no location limit.
- Operations hours: every day, 10 AM – 5 PM IST.
- Latency: reply within 5 seconds (p95); leads reach the sheet within 10 seconds of confirmation.

## Development Workflow and Stage Tracking

Each feature moves through these stages. Its stage is visible in git from the
artifacts that exist on its branch:

| Stage | Artifact | Spec Kit command | Commit prefix |
|---|---|---|---|
| 0. Intent | `intent.md` | — | `intent:` |
| 1. Specify | `specs/NNN-name/spec.md` | `/speckit-specify` (+ `/speckit-clarify`) | `spec:` |
| 2. Plan | `specs/NNN-name/plan.md` (+ research, data model, contracts) | `/speckit-plan` | `plan:` |
| 3. Tasks | `specs/NNN-name/tasks.md` | `/speckit-tasks` (+ `/speckit-analyze`) | `tasks:` |
| 4. Build | code + tests; tasks ticked in `tasks.md` | `/speckit-implement` | `feat(Gx):` / `fix(Gx):` / `test:` |
| 5. Verify | passing tests and evals in CI | — | `eval:` |
| 6. Release | merge to `main`, tag `vX.Y.Z` | — | `release:` |

Rules:
- One branch per feature, named `NNN-short-name` (created by `/speckit-specify`).
- A stage starts only when the previous stage's artifact has been reviewed.
  Code is not written before `tasks.md` exists.
- Every pull request states the feature folder, the stage it completes, and the
  intent goal IDs it serves (see the PR template).
- Commit messages use the prefixes above so `git log --oneline` reads as a
  stage timeline.

## Governance

This constitution overrides other practices in this repository. Amendments are
made by pull request with a short rationale, and bump the version: MAJOR for
removing or redefining a principle, MINOR for adding one, PATCH for wording.
Reviewers check every PR against these principles; any deviation must be
justified in the plan's complexity tracking section. Runtime guidance for
agents is in [`CLAUDE.md`](../../CLAUDE.md).

**Version**: 1.1.1 | **Ratified**: 2026-09-29 | **Last Amended**: 2026-09-29 (1.1.0 added Principle VI; 1.1.1 tutee-initiated only, no templates)
