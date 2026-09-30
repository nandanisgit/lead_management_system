# lead_management_system

Captures tutor-search leads from tutees over WhatsApp through a human-like
conversation and saves confirmed leads into the operational Google Sheet.

## How this repo is built (AI-native SDLC)

| Stage | Where to look |
|---|---|
| 0. Intent | [`intent.md`](intent.md) — why the system exists and what "done" means |
| Rules | [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — principles and workflow |
| 1–3. Spec, plan, tasks | `specs/NNN-feature/` — `spec.md`, `plan.md`, `tasks.md` (one branch per feature) |
| 4–5. Build and verify | code, tests and evals, run in CI |
| 6. Release | merges to `main`, tagged `vX.Y.Z` |

The workflow uses [GitHub Spec Kit](https://github.github.com/spec-kit/) with
Claude Code. In Claude Code, run the stages in order:

```
/speckit-specify   → spec.md
/speckit-clarify   → (optional) resolve ambiguities
/speckit-plan      → plan.md, data model, contracts
/speckit-tasks     → tasks.md
/speckit-analyze   → (optional) consistency check
/speckit-implement → code + tests, ticking off tasks
```

Commit messages use stage prefixes (`spec:`, `plan:`, `tasks:`, `feat(G3):`,
`eval:`, `release:`), so `git log --oneline` shows the stage history.
Agent guidance is in [`CLAUDE.md`](CLAUDE.md); coding rules in
[`docs/coding-guidelines.md`](docs/coding-guidelines.md).

## Where things are configured

| To change… | Edit |
|---|---|
| Tutor-requirement fields, allowed values, questions, summary, sheet columns | `config/requirement.yaml` |
| The assistant's fixed texts and language markers | `config/messages.yaml` |
| Models, limits, timeouts, retention, schedules, costs | `config/settings.yaml` |
| Model provider: free local Ollama (default for now) or Claude | `llm.provider` in `config/settings.yaml` — see [quickstart](specs/001-whatsapp-lead-capture/quickstart.md#free-local-model-ollama-for-the-first-days) |
| Secrets (API keys, sheet ID) | `.env` (copy `.env.example`) |
