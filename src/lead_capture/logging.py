"""JSON logs with IDs only (FR-027). Phone numbers are scrubbed; personal fields are dropped."""

from __future__ import annotations

import json
import logging
import re

PHONE = re.compile(r"\+?\d[\d \-]{8,}\d")
FORBIDDEN_EXTRA = {
    "body",
    "text",
    "person_name",
    "contact_name",
    "student_name",
    "guardian_name",
    "phone",
    "wa_number",
    "whatsapp_number",
    "email",
    "area",
    "profile_name",
}
_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def scrub(value: str) -> str:
    return PHONE.sub("[redacted]", value)


class PiiFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(str(record.msg))
        if record.args:
            record.args = tuple(scrub(str(a)) for a in record.args)
        for key in list(record.__dict__):
            if key in FORBIDDEN_EXTRA and key not in _STD:
                delattr(record, key)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"level": record.levelname, "logger": record.name, "event": record.getMessage()}
        for key, value in record.__dict__.items():
            if key not in _STD and key not in FORBIDDEN_EXTRA:
                out[key] = value if isinstance(value, int | float | bool) else scrub(str(value))
        if record.exc_info:
            out["error"] = record.exc_info[0].__name__ if record.exc_info[0] else "unknown"
        return json.dumps(out, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
