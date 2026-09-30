from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from lead_capture.store import queries
from lead_capture.store.models import Contact, Conversation, LeadOutbox, Message


def test_wa_message_id_unique(session_factory):
    with session_factory() as s:
        c = queries.get_or_create_contact(s, "+919999900001")
        assert queries.store_message(s, c.id, None, "m1", "in", "text", "hi") is True
        assert queries.store_message(s, c.id, None, "m1", "in", "text", "hi") is False
        s.commit()
        assert s.query(Message).count() == 1


def test_one_active_conversation_per_contact_and_student(session_factory):
    with session_factory() as s:
        c = queries.get_or_create_contact(s, "+919999900001")
        s.add(
            Conversation(
                contact_id=c.id, state="in_progress", student_key="aarav", source="organic"
            )
        )
        s.commit()
        s.add(
            Conversation(
                contact_id=c.id, state="in_progress", student_key="aarav", source="organic"
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        # a completed one for the same student is fine, and another student is fine
        s.add(
            Conversation(contact_id=c.id, state="completed", student_key="aarav", source="organic")
        )
        s.add(
            Conversation(contact_id=c.id, state="in_progress", student_key="riya", source="organic")
        )
        s.commit()


def test_outbox_primary_key_and_utc_timestamps(session_factory):
    ist = timezone(timedelta(hours=5, minutes=30))
    at = datetime(2026, 9, 29, 15, 0, tzinfo=ist)
    with session_factory() as s:
        s.add(LeadOutbox(lead_id="L-1", row={}, created_at=at))
        s.commit()
        s.add(LeadOutbox(lead_id="L-1", row={}))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        got = s.get(LeadOutbox, "L-1").created_at
        assert got.tzinfo is not None and got == at and got.astimezone(UTC).hour == 9


def test_active_conversation_lookup(session_factory):
    with session_factory() as s:
        c = queries.get_or_create_contact(s, "+919999900001", profile_name="Priya")
        assert s.query(Contact).one().wa_profile_name == "Priya"
        assert queries.active_conversation(s, c.id) is None
        conv = queries.start_conversation(s, c.id, source="organic")
        s.commit()
        assert queries.active_conversation(s, c.id).id == conv.id
