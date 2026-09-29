"""Drain the lead outbox into the LeadRepository (research R6). Exactly once, never lost."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import or_, select

from lead_capture.ports.leads import LeadRow, RepositoryContractError, RepositoryUnavailable
from lead_capture.services import Services
from lead_capture.store.models import LeadOutbox

log = logging.getLogger(__name__)


def drain_once(services: Services) -> int:
    """Write pending leads whose retry time has come. Returns how many were synced."""
    cfg = services.settings.leads
    now = services.clock.now()
    synced = 0
    with services.sessions() as db:
        pending = db.scalars(
            select(LeadOutbox)
            .where(
                LeadOutbox.status == "pending",
                or_(LeadOutbox.next_attempt_at.is_(None), LeadOutbox.next_attempt_at <= now),
            )
            .order_by(LeadOutbox.created_at)
        ).all()
        for item in pending:
            try:
                services.leads.append_lead(LeadRow.model_validate(item.row))
            except (RepositoryUnavailable, RepositoryContractError) as exc:
                item.attempts += 1
                item.last_error = type(exc).__name__
                delay = min(
                    cfg.retry_base_seconds * 2 ** (item.attempts - 1), cfg.max_backoff_seconds
                )
                if isinstance(exc, RepositoryContractError):
                    delay = cfg.max_backoff_seconds
                    log.error("outbox_contract_error", extra={"lead_id": item.lead_id})
                item.next_attempt_at = now + timedelta(seconds=delay)
                log.warning(
                    "outbox_retry", extra={"lead_id": item.lead_id, "attempts": item.attempts}
                )
                continue
            item.status = "synced"
            item.synced_at = now
            item.last_error = None
            synced += 1
            log.info("lead_synced", extra={"lead_id": item.lead_id})
        db.commit()
    return synced
