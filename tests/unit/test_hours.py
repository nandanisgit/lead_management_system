from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from lead_capture.domain.hours import ContactWhen, format_ist, reply_by, when_team_contacts
from lead_capture.settings import load_settings

IST = ZoneInfo("Asia/Kolkata")
OPS = load_settings().ops


@pytest.mark.parametrize(
    "hour,minute,expected",
    [
        (15, 0, ContactWhen.TODAY),
        (10, 0, ContactWhen.TODAY),
        (16, 59, ContactWhen.TODAY),
        (8, 0, ContactWhen.AFTER_START_TODAY),
        (17, 0, ContactWhen.AFTER_START_TOMORROW),
        (19, 0, ContactWhen.AFTER_START_TOMORROW),
    ],
)
def test_when_team_contacts(hour, minute, expected):
    assert when_team_contacts(datetime(2026, 9, 29, hour, minute, tzinfo=IST), OPS) == expected


def test_reply_by_is_window_after_last_inbound():
    last = datetime(2026, 9, 29, 17, 0, tzinfo=IST)
    assert format_ist(reply_by(last, 24), "Asia/Kolkata") == "2026-09-30 17:00"
