"""X-Hub-Signature-256 verification (HMAC-SHA256 of the raw body with the app secret)."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

from lead_capture.ports.channel import SignatureError


def verify(headers: Mapping[str, str], body: bytes, app_secret: str | None) -> None:
    """Raise SignatureError unless X-Hub-Signature-256 is the body's HMAC with the app secret."""
    if not app_secret:
        raise SignatureError("WA_APP_SECRET not configured")
    lowered = {k.lower(): v for k, v in headers.items()}
    header = lowered.get("x-hub-signature-256", "")
    if not header.startswith("sha256="):
        raise SignatureError("missing signature")
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(header[len("sha256=") :], expected):
        raise SignatureError("bad signature")
