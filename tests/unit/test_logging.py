import json
import logging

from lead_capture.logging import JsonFormatter, PiiFilter


def render(msg, *args, **extra):
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
    for k, v in extra.items():
        setattr(rec, k, v)
    PiiFilter().filter(rec)
    return JsonFormatter().format(rec)


def test_phone_numbers_scrubbed_and_personal_fields_dropped():
    out = render(
        "sent to %s", "+91 99999 00001", body="hello Priya", contact_name="Priya", lead_id="L-1"
    )
    data = json.loads(out)
    assert "99999" not in out and "Priya" not in out and "hello" not in out
    assert data["lead_id"] == "L-1" and "[redacted]" in data["event"]


def test_ids_and_counts_kept():
    data = json.loads(render("turn_done", conversation_id=12, attempts=2))
    assert data["conversation_id"] == 12 and data["attempts"] == 2
