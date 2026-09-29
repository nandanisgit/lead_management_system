"""Lead and handoff IDs: L-YYYYMMDD-XXXX / H-YYYYMMDD-XXXX, XXXX = 4 random base32 chars."""

from __future__ import annotations

import secrets
from datetime import datetime

_BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _suffix() -> str:
    return "".join(secrets.choice(_BASE32) for _ in range(4))


def new_lead_id(at: datetime) -> str:
    return f"L-{at:%Y%m%d}-{_suffix()}"


def new_handoff_id(at: datetime) -> str:
    return f"H-{at:%Y%m%d}-{_suffix()}"
