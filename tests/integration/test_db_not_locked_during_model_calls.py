"""The database must be writable while the model is thinking (slow local models, R17 fix).

A webhook arriving mid-turn has to store its message; if the turn held SQLite's write lock
across a model call, that store failed with "database is locked".
"""

import sqlite3

from lead_capture.ports.llm import ExtractionResult, Signals
from lead_capture.store.db import make_engine, make_session_factory
from lead_capture.store.models import Base
from tests.integration.harness import Harness


def can_write(path) -> bool:
    """Try to take SQLite's write lock from another connection, without waiting long."""
    con = sqlite3.connect(path, timeout=0.2)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.rollback()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


async def test_no_write_lock_is_held_during_model_calls(tmp_path):
    path = tmp_path / "store.db"
    engine = make_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    h = Harness(make_session_factory(engine))
    seen: list[bool] = []

    def extraction(turn):
        seen.append(can_write(path))
        return ExtractionResult(fields={"subjects": ["Maths"]}, signals=Signals(language="en"))

    def reply(turn, instruction):
        seen.append(can_write(path))
        return "Could you tell me your name?"

    h.llm._default_reply = reply
    await h.say("Hi, I need a maths tutor")
    h.script(extraction)
    await h.say(choice="consent:yes")  # consent is saved, then the model reads the message
    h.script(extraction)
    await h.say("for my son")
    engine.dispose()
    assert seen and all(seen), seen
