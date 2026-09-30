"""Row identifiers such as L-20260929-K7QX (prefixes from config/requirement.yaml → sheet).

Why: IDs must be unique, readable by the operations team, and safe to retry with — the
outbox and the sheet use them to write each lead exactly once.
"""

from __future__ import annotations

import secrets
from datetime import datetime

_BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_SUFFIX_LENGTH = 4


def new_id(prefix: str, at: datetime) -> str:
    """``<prefix>-YYYYMMDD-XXXX`` with XXXX = random base32 characters."""
    suffix = "".join(secrets.choice(_BASE32) for _ in range(_SUFFIX_LENGTH))
    return f"{prefix}-{at:%Y%m%d}-{suffix}"
