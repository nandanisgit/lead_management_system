"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
from lead_capture.domain.schema import RequirementSchema, get_schema
from lead_capture.store.db import Base, make_engine, make_session_factory


@pytest.fixture
def session_factory():
    """A fresh in-memory SQLite store per test."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def schema() -> RequirementSchema:
    """The real requirement schema from config/requirement.yaml."""
    return get_schema()


def memory_repo(schema: RequirementSchema | None = None, **kw) -> InMemoryLeadRepository:
    """In-memory lead register with the configured layouts."""
    schema = schema or get_schema()
    return InMemoryLeadRepository(
        schema.leads_layout(), schema.handoffs_layout(), timezone="Asia/Kolkata", **kw
    )
