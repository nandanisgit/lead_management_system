"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from lead_capture.store.db import Base, make_engine, make_session_factory


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()
