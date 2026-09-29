"""Shared contract suite for every LeadRepository adapter.

``ctx`` provides: ``repo`` (fresh, correct headers), ``bad_headers_repo()``,
``ops_write(lead_id, column_letter, value)`` simulating an operations edit,
``lead_values(lead_id) -> list`` (full row incl. AA–AC), ``mark_resolved(handoff_id)``.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from lead_capture.ports.leads import HandoffRow, LeadRepository, LeadRow, RepositoryContractError

IST = ZoneInfo("Asia/Kolkata")


def make_lead(lead_id="L-20260929-AAAA", created_at="2026-09-29 15:00", **kw) -> LeadRow:
    base = dict(
        lead_id=lead_id,
        created_at=created_at,
        whatsapp_number="+919999900001",
        contact_name="Priya",
        relationship="parent",
        student_name="Aarav",
        grade_level="Class 8",
        board="CBSE",
        subjects="Maths, Science",
        mode="home",
        area="Dwarka Sector 12",
        city="Delhi",
        schedule="weekdays after 5 pm",
        start_date="ASAP",
        budget_min=600,
        budget_max=600,
        budget_unit="per hour",
        language="Hindi",
        source="organic",
        consent_at="2026-09-29 14:50",
    )
    base.update(kw)
    return LeadRow(**base)


def make_handoff(handoff_id="H-20260929-AAAA", time="2026-09-29 15:00") -> HandoffRow:
    return HandoffRow(
        handoff_id=handoff_id,
        time=time,
        whatsapp_number="+919999900001",
        name="Priya",
        reason="requested",
        captured_so_far="Class 8 CBSE, Maths",
        reply_by="2026-09-30 15:00",
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
    assert ctx.repo.exists(lead.lead_id)
    assert ctx.lead_values(lead.lead_id)[0] == lead.lead_id
    assert ctx.lead_count() == 1


def check_never_touches_ops_columns(ctx):
    lead = make_lead()
    ctx.repo.append_lead(lead)
    ctx.ops_write(lead.lead_id, "AA", "Ravi")
    ctx.repo.append_lead(lead)  # retry must not clear ops data
    values = ctx.lead_values(lead.lead_id)
    assert values[25] == "NEW"  # Z
    assert values[26] == "Ravi"  # AA untouched


def check_formula_guard(ctx):
    lead = make_lead(lead_id="L-20260929-BBBB", notes='=HYPERLINK("x")', contact_name="@me")
    ctx.repo.append_lead(lead)
    values = ctx.lead_values(lead.lead_id)
    assert values[21].startswith("'=")
    assert values[3] == "'@me"


def check_delete_by_id(ctx):
    lead = make_lead()
    ctx.repo.append_lead(lead)
    assert ctx.repo.delete_lead(lead.lead_id) is True
    assert not ctx.repo.exists(lead.lead_id)
    assert ctx.repo.delete_lead(lead.lead_id) is False


def check_delete_created_before(ctx):
    ctx.repo.append_lead(make_lead("L-20250101-OLD1", created_at="2025-01-01 10:00"))
    ctx.repo.append_lead(make_lead("L-20260929-NEW1", created_at="2026-09-29 10:00"))
    removed = ctx.repo.delete_leads_created_before(datetime(2026, 1, 1, tzinfo=IST))
    assert removed == 1
    assert ctx.repo.exists("L-20260929-NEW1") and not ctx.repo.exists("L-20250101-OLD1")


def check_handoffs(ctx):
    ctx.repo.append_handoff(make_handoff())
    ctx.repo.update_handoff_reply_by("H-20260929-AAAA", "2026-09-30 18:00")
    assert ctx.repo.resolved_handoffs() == []
    ctx.mark_resolved("H-20260929-AAAA")
    assert ctx.repo.resolved_handoffs() == ["H-20260929-AAAA"]
    ctx.repo.append_handoff(make_handoff("H-20250101-OLD1", time="2025-01-01 10:00"))
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
