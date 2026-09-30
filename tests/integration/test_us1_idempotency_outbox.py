from sqlalchemy import select

from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
from lead_capture.domain.schema import get_schema
from lead_capture.jobs.outbox import drain_once
from lead_capture.ports.leads import RepositoryUnavailable
from lead_capture.store.models import LeadOutbox, Message
from tests.integration.harness import Harness, to_summary


async def test_duplicate_webhook_delivery(session_factory):
    h = Harness(session_factory)
    m = h.message("Hi, need a tutor", msg_id="wamid.DUP")
    await h.deliver(m, m)
    await h.deliver(m)
    assert len(h.channel.sent) == 1
    with session_factory() as s:
        assert s.query(Message).filter(Message.direction == "in").count() == 1


class FlakyRepo(InMemoryLeadRepository):
    """In-memory register that fails with a transient error while ``down`` is True."""

    def __init__(self):
        schema = get_schema()
        super().__init__(schema.leads_layout(), schema.handoffs_layout(), timezone="Asia/Kolkata")
        self.down = True

    def append_lead(self, row):
        if self.down:
            raise RepositoryUnavailable("http_503")
        super().append_lead(row)


async def test_sheet_down_at_confirmation_then_recovers(session_factory):
    repo = FlakyRepo()
    h = Harness(session_factory, leads=repo)
    await to_summary(h)
    [close] = await h.say(choice="confirm:yes")
    assert "Thank you" in close.text  # tutee confirmed regardless
    assert repo.leads == []
    with session_factory() as s:
        item = s.scalars(select(LeadOutbox)).one()
        assert item.status == "pending" and item.attempts == 1 and item.next_attempt_at

    repo.down = False
    h.clock.advance(seconds=h.settings.leads.retry_base_seconds)
    assert drain_once(h.sv) == 1
    assert drain_once(h.sv) == 0  # never duplicated
    assert len(repo.leads) == 1
    with session_factory() as s:
        assert s.scalars(select(LeadOutbox)).one().status == "synced"
