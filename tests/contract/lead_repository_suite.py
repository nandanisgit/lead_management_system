"""Shared contract suite for every LeadRepository adapter.

Rows are built from the configured layout and cells are read by header name, so the suite
keeps working when columns are added or removed in config/requirement.yaml.

``ctx`` provides: ``repo`` (fresh, correct headers), ``bad_headers_repo()``,
``ops_write(lead_id, header, value)``, ``lead_values(lead_id) -> list`` (full row),
``lead_count()``, ``mark_resolved(handoff_id)``.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from lead_capture.domain.schema import get_schema
from lead_capture.ports.leads import LeadRepository, RepositoryContractError, SheetRow

IST = ZoneInfo("Asia/Kolkata")
SCHEMA = get_schema()
LEADS = SCHEMA.leads_layout()
HANDOFFS = SCHEMA.handoffs_layout()


def make_row(layout, **cells) -> SheetRow:
    """A row for ``layout`` with the given cells (by header); other bot cells are filled."""
    values = [f"v{i}" for i in range(layout.bot_columns)]
    for header, value in cells.items():
        values[layout.index(header)] = value
    return SheetRow(values=values)


def make_lead(lead_id="L-20260929-AAAA", created="2026-09-29 15:00", **cells) -> SheetRow:
    return make_row(
        LEADS,
        **{LEADS.headers[LEADS.key_index]: lead_id, LEADS.headers[LEADS.created_index]: created},
        **cells,
    )


def make_handoff(handoff_id="H-20260929-AAAA", created="2026-09-29 15:00") -> SheetRow:
    return make_row(
        HANDOFFS,
        **{
            HANDOFFS.headers[HANDOFFS.key_index]: handoff_id,
            HANDOFFS.headers[HANDOFFS.created_index]: created,
        },
    )


def check_is_repository(ctx):
    assert isinstance(ctx.repo, LeadRepository)
    ctx.repo.check_headers()


def check_header_mismatch_raises(ctx):
    with pytest.raises(RepositoryContractError):
        ctx.bad_headers_repo().check_headers()


def check_append_is_idempotent(ctx):
    lead = make_lead()
    ctx.repo.append_lead(lead)
    ctx.repo.append_lead(lead)
    assert ctx.repo.exists("L-20260929-AAAA") and ctx.lead_count() == 1


def check_never_touches_ops_columns(ctx):
    ops_header = LEADS.headers[LEADS.bot_columns]  # first ops-owned column
    ctx.repo.append_lead(make_lead())
    ctx.ops_write("L-20260929-AAAA", ops_header, "Ravi")
    ctx.repo.append_lead(make_lead())  # a retry must not clear ops data
    values = ctx.lead_values("L-20260929-AAAA")
    assert values[LEADS.index(ops_header)] == "Ravi"
    assert len(values) == len(LEADS.headers)


def check_formula_guard(ctx):
    notes, name = LEADS.headers[-4], LEADS.headers[3]
    ctx.repo.append_lead(make_lead("L-20260929-BBBB", **{notes: '=HYPERLINK("x")', name: "@me"}))
    values = ctx.lead_values("L-20260929-BBBB")
    assert values[LEADS.index(notes)].startswith("'=")
    assert values[LEADS.index(name)] == "'@me"


def check_delete_by_id(ctx):
    ctx.repo.append_lead(make_lead())
    assert ctx.repo.delete_lead("L-20260929-AAAA") is True
    assert not ctx.repo.exists("L-20260929-AAAA")
    assert ctx.repo.delete_lead("L-20260929-AAAA") is False


def check_delete_created_before(ctx):
    ctx.repo.append_lead(make_lead("L-20250101-OLD1", created="2025-01-01 10:00"))
    ctx.repo.append_lead(make_lead("L-20260929-NEW1", created="2026-09-29 10:00"))
    assert ctx.repo.delete_leads_created_before(datetime(2026, 1, 1, tzinfo=IST)) == 1
    assert ctx.repo.exists("L-20260929-NEW1") and not ctx.repo.exists("L-20250101-OLD1")


def check_handoffs(ctx):
    ctx.repo.append_handoff(make_handoff())
    ctx.repo.append_handoff(make_handoff())  # idempotent
    ctx.repo.update_handoff_reply_by("H-20260929-AAAA", "2026-09-30 18:00")
    assert ctx.repo.resolved_handoffs() == []
    ctx.mark_resolved("H-20260929-AAAA")
    assert ctx.repo.resolved_handoffs() == ["H-20260929-AAAA"]
    ctx.repo.append_handoff(make_handoff("H-20250101-OLD1", created="2025-01-01 10:00"))
    assert ctx.repo.delete_handoffs_before(datetime(2026, 1, 1, tzinfo=IST)) == 1


ALL_CHECKS = [
    check_is_repository,
    check_header_mismatch_raises,
    check_append_is_idempotent,
    check_never_touches_ops_columns,
    check_formula_guard,
    check_delete_by_id,
    check_delete_created_before,
    check_handoffs,
]
