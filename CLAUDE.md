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

_To be filled in once the tech stack is chosen in the first plan (install, run, test, eval, lint)._
