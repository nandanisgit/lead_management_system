"""ConversationLock port — one turn at a time per contact."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class ConversationLock(Protocol):
    def hold(self, key: str) -> AbstractAsyncContextManager[None]: ...
