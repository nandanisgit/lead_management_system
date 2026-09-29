# CLAUDE.md

Guidance for Claude Code (and other coding agents) working in this repository.

## Read first, every task

1. [`intent.md`](intent.md) — what this system is for, goals G1–G7, non-goals, success criteria.
2. [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — how we build it: principles, workflow, stage rules.
3. The current feature folder under `specs/NNN-name/` (spec → plan → tasks), if you are working on a feature.

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

Code lives in `src/lead_capture/`; prompts in `prompts/`; allowed values in `config/lists.yaml`; evals in `evals/`; load tests in `load/`. Scaling path: `specs/001-whatsapp-lead-capture/research.md` R14.
