import re
from datetime import datetime

from lead_capture.domain.ids import new_handoff_id, new_lead_id


def test_lead_and_handoff_id_format():
    at = datetime(2026, 9, 29, 15, 0)
    assert re.fullmatch(r"L-20260929-[A-Z2-7]{4}", new_lead_id(at))
    assert re.fullmatch(r"H-20260929-[A-Z2-7]{4}", new_handoff_id(at))


def test_ids_are_random():
    at = datetime(2026, 9, 29)
    assert len({new_lead_id(at) for _ in range(200)}) > 190
