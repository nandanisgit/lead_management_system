"""JSON logs with IDs only (FR-027).

Why: logs are read by more people and kept longer than the data itself, so they must never
contain personal data. Phone numbers are scrubbed from messages, and any log field named
after a personal-data field (the schema's ``pii: true`` fields plus the names below) is
dropped.
"""

from __future__ import annotations

import json
import logging
import re

PHONE = re.compile(r"\+?\d[\d \-]{8,}\d")
# Transport-level names that can carry personal data; requirement fields marked
# ``pii: true`` in config/requirement.yaml are added by ``register_pii_fields``.
FORBIDDEN_EXTRA = {"body", "text", "phone", "wa_number", "whatsapp_number", "profile_name"}
_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def scrub(value: str) -> str:
    """Replace anything that looks like a phone number."""
    return PHONE.sub("[redacted]", value)


class PiiFilter(logging.Filter):
    """Scrubs the message and removes personal-data fields from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Mutate the record in place; always keep it (returns True)."""
        record.msg = scrub(str(record.msg))
        if record.args:
            record.args = tuple(scrub(str(a)) for a in record.args)
        for key in list(record.__dict__):
            if key in FORBIDDEN_EXTRA and key not in _STD:
                delattr(record, key)
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: level, logger, event and the (safe) extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record; exceptions are reduced to their class name."""
        out = {"level": record.levelname, "logger": record.name, "event": record.getMessage()}
        for key, value in record.__dict__.items():
            if key not in _STD and key not in FORBIDDEN_EXTRA:
                out[key] = value if isinstance(value, int | float | bool) else scrub(str(value))
        if record.exc_info:
            out["error"] = record.exc_info[0].__name__ if record.exc_info[0] else "unknown"
        return json.dumps(out, ensure_ascii=False)


def register_pii_fields(names: set[str]) -> None:
    """Also drop log fields with these names (the schema's ``pii: true`` fields)."""
    FORBIDDEN_EXTRA.update(names)


def setup_logging(level: str = "INFO", pii_fields: set[str] | None = None) -> None:
    """Install the JSON handler with the PII filter; ``pii_fields`` come from the schema."""
    register_pii_fields(pii_fields or set())
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
