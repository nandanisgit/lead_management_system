# CLAUDE.md

Guidance for Claude Code (and other coding agents) working in this repository.

## Read first, every task

1. [`intent.md`](intent.md) — what this system is for, goals G1–G7, non-goals, success criteria.
2. [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — how we build it: principles, workflow, stage rules.
3. [`docs/coding-guidelines.md`](docs/coding-guidelines.md) — how code is written here: no hard-coding, interfaces, documentation.
4. The current feature folder under `specs/NNN-name/` (spec → plan → tasks), if you are working on a feature.

If a request conflicts with `intent.md` or the constitution, stop and ask.
If something is unclear, add it to the spec's open questions instead of guessing.

## Workflow (Spec Kit)

Work moves through stages, one feature branch at a time:

`/speckit-specify` → `/speckit-clarify` (optional) → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` (optional) → `/speckit-implement`

- Don't write application code until the feature's `tasks.md` exists.
- Tick tasks off in `tasks.md` as they are completed.
- Commit with stage prefixes: `spec:`, `plan:`, `tasks:`, `feat(G3):`, `fix(G5):`, `test:`, `eval:`, `release:`.
- Fill in the pull request template: feature folder, stage, goal IDs.

## Hard rules

- Never write to the Google Sheet from unvalidated model output; only confirmed, validated leads.
- All Google Sheets access goes through `LeadRepository`; the bot only appends and never overwrites ops-owned columns.
- No secrets, tokens or sheet IDs in code — use configuration / environment variables.
- No personal data in logs beyond IDs.
- Don't build anything in the intent's Non-goals list.
- Never call a vendor SDK (Anthropic, WhatsApp/Meta, Google) from conversation or domain code — go through `LLMClient`, `MessagingChannel`, `LeadRepository` and the other interfaces; vendor code lives only in its adapter module.
- Never hard-code performance or cost numbers (models, token limits, context size, timeouts, retries, concurrency, debounce, thresholds, schedules, retention, rates) — add them to `config/settings.yaml` with a validated default. See constitution Principle VI and research R16.
- Never hard-code tutor-requirement fields (names, allowed values, questions, labels, summary lines, sheet columns) in code, prompts or tests — they live only in `config/requirement.yaml`. Fixed texts live in `config/messages.yaml`. Adding or removing a field must not need a code change (docs/coding-guidelines.md §1).
- Every module, class and function gets a docstring saying why it exists (constitution Principle VII; ruff enforces it).

## Commands

Stack (from `specs/001-whatsapp-lead-capture/plan.md`): Python 3.12, FastAPI, Pydantic v2, SQLAlchemy + Alembic (SQLite), Anthropic SDK, Google Sheets API, APScheduler, Typer, pytest.

```bash
uv sync                          # install
uv run alembic upgrade head      # migrate local store
uv run pytest                    # tests (no network)
uv run lead-capture eval         # conversation evals (real model, simulated tutee)
uv run lead-capture load --profile capacity|burst|soak   # load tests (before release)
uv run lead-capture chat         # terminal chat with the engine
uv run uvicorn lead_capture.app:app --port 8000   # run the service
uv run ruff check . && uv run ruff format --check .   # lint
```

Code lives in `src/lead_capture/`; prompts in `prompts/`; settings in `config/settings.yaml`; requirement fields and allowed values in `config/requirement.yaml`; fixed texts in `config/messages.yaml`; evals in `evals/`; load tests in `load/`. Scaling path: `specs/001-whatsapp-lead-capture/research.md` R14.
