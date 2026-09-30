# Coding guidelines

Rules for everyone writing code in this repository — people and AI coding agents. They sit
under the constitution (`.specify/memory/constitution.md`, Principles VI and VII) and are
enforced by review, `ruff` and tests. `CLAUDE.md` links here; read this before writing code.

---

## 1. No hard-coding: one place for everything that can change

Anything that might change without a change in *behaviour* lives in configuration, not code.

| What | Where it lives | Never in |
|---|---|---|
| Tutor-requirement fields: names, types, allowed values, when required, questions, labels, model hints, summary lines, sheet columns | `config/requirement.yaml` | Python code, prompts, tests |
| Fixed texts the assistant sends, tap-option titles, language and currency markers, time display format | `config/messages.yaml` | Python code |
| Performance and cost numbers: models, token limits, context size, timeouts, retries, concurrency, debounce, thresholds, schedules, retention, rates, eval and load parameters | `config/settings.yaml` (override with `LC__GROUP__KEY` env vars) | Python code |
| Secrets: API keys, tokens, sheet ID, service-account path | environment variables (`.env`, never committed) | anywhere in the repo |
| The system prompt and extraction prompt | `prompts/*.md` | Python code |

Allowed in code, as a **named constant with a comment saying where it comes from**:

- protocol or platform rules that config must not change (e.g. WhatsApp: 3 reply buttons,
  10 list rows, 20-character button titles, 24-hour service window; API base URLs);
- data-contract formats that other systems depend on (e.g. the Lead ID pattern);
- generic parsing (e.g. Roman numerals for "class IX").

Checks that enforce this:

- `config/requirement.yaml` and `config/messages.yaml` are validated at start-up; unknown keys,
  unknown fields/lists/placeholders and misplaced sheet columns stop the service.
- `tests/unit/test_schema.py::test_adding_a_field_is_config_only` proves a field can be
  added without code.
- `tests/unit/test_fixed_texts.py` checks every configured text and question against the
  message limits.
- The architecture audit (tasks.md T129) fails the build on vendor imports outside
  `adapters/`, numeric performance/cost literals outside `config/settings.yaml`, and
  requirement field names written as literals in `src/` or `prompts/`.

### Adding or removing a requirement field

Only `config/requirement.yaml` changes (plus the sheet header itself):

1. **Define it** under `fields:` — `type` (`text`, `choice`, `multi_choice`, `grade`,
   `positive_int`, `int_range`, `date_or_asap`, `email_address`, `postal_code`) and that type's
   parameters; `required` (`true`, `false`, or `{when: <condition>}`); `label`, `ask` (en/hi);
   `llm.description`; `pii: true` if it is personal data; `options` pointing at a list under
   `lists:` for choice types; `buttons` if it should be offered as tap options.
2. **Ask it** — if it can be required, add it to an `ask_groups:` entry (the loader refuses a
   requirable field that is in no group).
3. **Show it** — optionally add a line or placeholder under `summary.lines` (both languages).
4. **Store it** — add a column under `sheet.leads.columns` *before* the `owner: ops` columns,
   then add the same header to the Leads tab in the Google Sheet (in the same position).
   `lead-capture check-sheet` confirms the sheet matches.
5. **Run** `uv run pytest` and `uv run lead-capture eval`. Update eval scenarios' `tutee_facts`
   if the new field is required.

Removing a field is the reverse: delete it from `fields:`, `ask_groups:`, `summary:` and
`sheet:` (the loader points at anything still referring to it), then delete the sheet column.

A new *kind* of value (not covered by an existing type) is the only reason to touch code:
add a validator in `src/lead_capture/domain/field_types.py`, its parameters in
`FieldSpec`, and tests.

Changing which fields are **required**, or the lifecycle, is a product decision: update
`intent.md` §6/§8 first (constitution Principle I).

## 2. Interfaces, not vendors

- Business code (`conversation/`, `domain/`, `jobs/`) talks only to the ports in
  `src/lead_capture/ports/`: `LLMClient`, `MessagingChannel`, `LeadRepository`, `TurnQueue`,
  `ConversationLock`, `Clock`.
- Vendor SDKs and external APIs (Anthropic, Meta/WhatsApp, Google) are imported only in
  `src/lead_capture/adapters/`. Adapters are chosen by name in `config/settings.yaml` via
  `registry.py`.
- Every port has a fake adapter, and every adapter — real or fake — passes the shared
  contract suite in `tests/contract/`.
- A channel's abilities (buttons, list rows, reply window) come from `Capabilities`; never
  assume WhatsApp in business code.

## 3. Documentation

Every module, class, method and function has a docstring that says **why it exists** — the
need it serves — not just what the next line does.

- **Module docstring**: its purpose and why it is separate ("Why: …"), plus links to the
  spec/contract/research section it implements (e.g. FR-022, research R6).
- **Class / function docstring**: one-line summary in the imperative or descriptive form,
  then (if useful) a blank line and the reasons, rules and non-obvious behaviour: what
  happens on failure, what it must never do, which setting controls it.
- Private helpers (`_name`) are documented too, briefly.
- Refer to requirements by ID (`FR-013`, `SC-002`, `research R16`) so readers can trace a
  line of code back to the decision behind it.
- Comments explain *why*, never restate *what*.
- `ruff` enforces docstrings (pydocstyle, Google convention) on everything public in `src/`
  and `evals/`; review enforces the rest. Tests and migrations are exempt, but test names
  should read as the behaviour they check.

Example:

```python
def next_fields(missing: list[str], schema: RequirementSchema, max_questions: int) -> list[str]:
    """The next fields to ask.

    The first ask group with a missing field, capped at ``max_questions`` (FR-001).
    """
```

## 4. Data and privacy

- The model's output is a proposal. Only values validated by `Requirement.apply` are stored,
  and only the CONFIRMING → COMPLETED transition creates a lead (constitution Principle II).
- The bot writes only the bot-owned sheet columns and never the `owner: ops` ones.
- No personal data in logs: log IDs and counts. Mark personal fields `pii: true` in
  `config/requirement.yaml` so the log filter drops them.
- No templates or business-initiated messages: every send is a reply inside the channel's
  reply window (FR-022).

## 5. Tests and evals

- Write the test first and see it fail (constitution Principle III).
- Tests never depend on column positions or field lists written in the test: read cells by
  header (`layout.index("Notes")`) and fields from the schema.
- Tests never read the developer's `.env`; set the environment variables a test needs.
- Changes to conversation behaviour, prompts or `config/requirement.yaml` /
  `config/messages.yaml` must keep `uv run lead-capture eval` passing.

## 6. Style

- Python 3.12, `ruff` (lint + format, line length 100). `uv run ruff check . && uv run ruff format --check .`
- Type hints on every public function.
- Small functions; one reason to change per module.
- Commit messages use the stage prefixes in `CLAUDE.md`; tick tasks in `tasks.md` in the same
  commit.

## Checklist for a pull request

- [ ] No new hard-coded field names, texts or tunable numbers in `src/` (config instead)
- [ ] No vendor imports outside `adapters/`
- [ ] Every new module/class/function has a docstring saying why it exists
- [ ] Tests first; `uv run pytest` and `ruff` pass; evals pass if conversation behaviour changed
- [ ] Docs updated where behaviour or configuration changed (spec, research, contracts)
