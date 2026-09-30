import re
from datetime import datetime

from lead_capture.domain.ids import new_id


def test_id_format_and_randomness():
    at = datetime(2026, 9, 29, 15, 0)
    assert re.fullmatch(r"L-20260929-[A-Z2-7]{4}", new_id("L", at))
    assert len({new_id("H", at) for _ in range(200)}) > 190
