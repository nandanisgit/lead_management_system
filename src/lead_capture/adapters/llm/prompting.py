"""Vendor-neutral prompt building shared by every LLMClient adapter.

Why: each model provider (Claude, Ollama, …) must see the same instructions, the same
response schema and the same trimmed context, so a provider swap changes only transport and
output format — never what the model is asked. Field names come from config/requirement.yaml
(passed in as ``fields_schema``); the signals are part of the code contract (ports.llm.Signals).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lead_capture.ports.llm import (
    ExtractionResult,
    Instruction,
    Signals,
    TokenUsage,
    TurnContext,
)
from lead_capture.settings import ROOT

PROMPTS: Path = ROOT / "prompts"

SIGNAL_SCHEMA: dict[str, dict[str, Any]] = {
    "language": {"type": "string", "enum": ["en", "hi", "other"]},
    "consent": {"type": "string", "enum": ["given", "declined", "none"]},
    "confirms_summary": {"type": "boolean"},
    "wants_human": {"type": "boolean"},
    "not_interested": {"type": "boolean"},
    "accepts_online": {"type": "boolean"},
    "new_student": {
        "type": "boolean",
        "description": "Tutee is starting a requirement for a different student",
    },
    "deletion_request": {"type": "boolean"},
    "complaint_or_sensitive": {"type": "boolean"},
    "understood": {
        "type": "boolean",
        "description": "False if the message could not be understood",
    },
    "likely_minor_alone": {
        "type": "boolean",
        "description": "The person chatting appears to be under 18 and no parent is involved",
    },
    "off_topic": {
        "type": "boolean",
        "description": "The message is not about the tutoring requirement",
    },
    "asks_fees_or_tutors": {
        "type": "boolean",
        "description": "The tutee asks about fees, rates, tutor names or availability",
    },
}


def response_schema(fields_schema: dict[str, Any]) -> dict[str, Any]:
    """JSON schema of one extraction answer: ``fields`` from config, ``signals`` from code.

    Used as the Claude tool's input schema and as Ollama's structured-output ``format``.
    """
    return {
        "type": "object",
        "properties": {
            "fields": fields_schema,
            "signals": {
                "type": "object",
                "properties": SIGNAL_SCHEMA,
                "required": ["language", "understood"],
                "additionalProperties": False,
            },
        },
        "required": ["fields", "signals"],
    }


def field_guide(fields_schema: dict[str, Any]) -> str:
    """One short line per field: name, description and allowed values.

    Why: small local models are slow on long prompts. The full JSON schema is already
    enforced by the provider's structured-output mode, so the prompt only needs the meaning
    of each field — about half the tokens of pasting the schema.
    """
    lines = []
    for name, prop in fields_schema.get("properties", {}).items():
        line = f"- {name}: {prop.get('description', '')}".rstrip()
        if prop.get("enum"):
            line += f" (one of: {', '.join(map(str, prop['enum']))})"
        if prop.get("type") == "array":
            line += " (a list)"
        elif prop.get("type") == "integer":
            line += " (a whole number)"
        lines.append(line)
    return "\n".join(lines)


def read_prompt(name: str) -> str:
    """Text of ``prompts/<name>`` — prompts are files so they can be tuned without code."""
    return (PROMPTS / name).read_text()


def extraction_system(output_prompt: str, **values: str) -> str:
    """The extraction system prompt plus the provider's output-format line.

    ``output_prompt`` is a file in ``prompts/`` (tool call vs JSON answer); ``values`` fill
    its ``{placeholders}``.
    """
    tail = read_prompt(output_prompt)
    for key, value in values.items():
        tail = tail.replace("{" + key + "}", value)
    return read_prompt("extraction.md").rstrip() + "\n\n" + tail


def reply_system(max_questions: int, max_words: int) -> str:
    """The reply system prompt with the conversation limits from settings filled in."""
    return (
        read_prompt("assistant.md")
        .replace("{max_questions}", str(max_questions))
        .replace("{max_words}", str(max_words))
    )


def transcript(turn: TurnContext, limit: int) -> str:
    """The last ``limit`` messages as plain lines (context size is a cost setting)."""
    lines = turn.transcript[-limit:]
    return "\n".join(f"{'Tutee' if ln.role == 'tutee' else 'Assistant'}: {ln.text}" for ln in lines)


def extraction_content(turn: TurnContext, context_messages: int) -> str:
    """User message for extraction: validated state, what is missing, recent messages."""
    return (
        f"Captured so far (validated): {json.dumps(turn.state, ensure_ascii=False)}\n"
        f"Still missing: {', '.join(turn.missing) or 'nothing'}\n"
        f"The assistant's last question asked for: {', '.join(turn.asked) or 'nothing specific'}\n"
        f"Conversation stage: {turn.stage}\n\n"
        f"Recent messages (oldest first):\n{transcript(turn, context_messages)}"
    )


def reply_content(turn: TurnContext, instruction: Instruction, context_messages: int) -> str:
    """User message for a reply: state, language, strictness, messages and the instruction."""
    language = "Hindi/Hinglish (Roman script)" if turn.language == "hi" else "English"
    return (
        f"Captured details: {json.dumps(turn.state, ensure_ascii=False)}\n"
        f"Still missing: {', '.join(turn.missing) or 'nothing'}\n"
        f"Reply language: {language}\n"
        f"Strict mode: {'yes' if instruction.strict else 'no'}\n\n"
        f"Recent messages (oldest first):\n{transcript(turn, context_messages)}\n\n"
        f"Instruction: {instruction.kind} {json.dumps(instruction.params, ensure_ascii=False)}"
    )


def parse_extraction(
    payload: dict[str, Any], known_fields: set[str], usage: TokenUsage
) -> ExtractionResult:
    """Turn a model's raw answer into an ExtractionResult with unknown fields dropped.

    Bad signals fall back to defaults; field values are only proposals and are validated
    later by the engine (constitution Principle II).
    """
    try:
        signals = Signals.model_validate(payload.get("signals") or {})
    except ValueError:
        signals = Signals()
    fields = payload.get("fields")
    result = ExtractionResult(
        fields=fields if isinstance(fields, dict) else {}, signals=signals, usage=usage
    )
    return result.only_known_fields(known_fields)
