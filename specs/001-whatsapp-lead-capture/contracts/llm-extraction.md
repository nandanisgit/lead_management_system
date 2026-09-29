# Contract: Language-Model Extraction Tool

The engine reaches the model only through the `LLMClient` interface
(`extract`, `write_reply`; research R16). `AnthropicLLMClient` implements it
with the tool below; another provider's adapter must return the same
`ExtractionResult`. Models, token limits, context size and temperatures come
from `config/settings.yaml` (`llm.*`). Turns that code can answer itself are
skipped when `llm.skip_for_deterministic_turns` is on.

Each turn that needs the model, the engine requests a forced tool call
to `record_requirements`. The tool input is a **proposal only**: every value is
re-validated by code (the `Requirement` model in
[data-model.md](../data-model.md)) before it is stored. Unknown or invalid
values are dropped and trigger a clarifying question.

## Tool definition

```json
{
  "name": "record_requirements",
  "description": "Record every tutoring requirement detail found in the tutee's latest message(s), plus conversation signals. Include only details the tutee actually stated; never infer budget or schedule. Omit fields not mentioned.",
  "input_schema": {
    "type": "object",
    "properties": {
      "fields": {
        "type": "object",
        "properties": {
          "contact_name":     {"type": "string"},
          "relationship":     {"type": "string", "enum": ["parent", "student", "other"]},
          "student_name":     {"type": "string"},
          "grade_level":      {"type": "string"},
          "board":            {"type": "string"},
          "subjects":         {"type": "array", "items": {"type": "string"}},
          "mode":             {"type": "string", "enum": ["online", "home", "either"]},
          "area":             {"type": "string"},
          "city":             {"type": "string"},
          "pincode":          {"type": "string"},
          "schedule":         {"type": "string"},
          "start_date":       {"type": "string", "description": "ASAP or YYYY-MM-DD"},
          "budget_min":       {"type": "integer"},
          "budget_max":       {"type": "integer"},
          "budget_unit":      {"type": "string", "enum": ["per_hour", "per_month"]},
          "goal":             {"type": "string"},
          "sessions_per_week":{"type": "integer"},
          "tutor_preferences":{"type": "string"},
          "level_notes":      {"type": "string"},
          "email":            {"type": "string"},
          "guardian_name":    {"type": "string"},
          "guardian_relationship": {"type": "string", "enum": ["mother", "father", "guardian", "other"]}
        },
        "additionalProperties": false
      },
      "signals": {
        "type": "object",
        "properties": {
          "language":        {"type": "string", "enum": ["en", "hi", "other"]},
          "consent":         {"type": "string", "enum": ["given", "declined", "none"]},
          "confirms_summary":{"type": "boolean"},
          "wants_human":     {"type": "boolean"},
          "not_interested":  {"type": "boolean"},
          "accepts_online":  {"type": "boolean"},
          "new_student":     {"type": "boolean", "description": "Tutee is starting a requirement for a different student"},
          "deletion_request":{"type": "boolean"},
          "complaint_or_sensitive": {"type": "boolean"},
          "understood":      {"type": "boolean", "description": "False if the message could not be understood"},
          "likely_minor_alone": {"type": "boolean", "description": "The person chatting appears to be under 18 and no parent is involved"}
        },
        "required": ["language", "understood"],
        "additionalProperties": false
      }
    },
    "required": ["fields", "signals"]
  }
}
```

## Reply-writing call

A second call (no tools) writes the tutee-facing message. Its input is built by
code and includes:

- the system prompt (`prompts/assistant.md`: tone, language, rules from intent §7);
- the recent transcript (last `llm.context_messages` messages, default 6);
- the validated state and the list of still-missing required fields;
- one **instruction** chosen by code, e.g. `ASK: grade_level, board`,
  `SUMMARISE_AND_CONFIRM`, `OFFER_ONLINE_OUT_OF_AREA`, `CLOSE_COMPLETED(today)`,
  `HANDOFF_ACK(after_10am)`, `ASK_FOR_TEXT`, `LANGUAGE_UNSUPPORTED`,
  `ASK_GUARDIAN` (FR-029).
- a `strict` flag when the conversation is `minor_alone`: no small talk, off-topic
  messages get a one-line redirect only.

## Post-generation checks (code)

| Check | On failure |
|---|---|
| ≤ `conversation.max_questions_per_message` questions and ≤ `conversation.max_words_per_message` words | regenerate up to `llm.max_regenerations` times, then use the fixed text for the instruction |
| no ₹/Rs/number-with-currency not already stated by the tutee | same |
| reply language matches `Contact.language` | same |
| summary replies list exactly the validated values | build the summary from code, let the model phrase only the lead-in |
