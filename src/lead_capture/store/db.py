"""SQLAlchemy engine/session for the bot working store (SQLite WAL in v1, PostgreSQL later)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Stores timezone-aware datetimes as naive UTC; returns aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime given; use timezone-aware datetimes")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        if url in ("sqlite://", "sqlite:///:memory:"):
            engine = create_engine(
                "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
        else:
            path = url.split("sqlite:///", 1)[-1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
