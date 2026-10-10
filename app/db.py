"""Database engine, session, and models."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

from pydantic import NaiveDatetime
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, create_engine

from app.config import settings

# Make sure the local data directory exists for the dev SQLite file.
Path("data").mkdir(exist_ok=True)


def _connect_args() -> dict:
    url = settings.database_url
    if url.startswith("sqlite+libsql"):
        args: dict = {}
        if settings.turso_auth_token:
            args["auth_token"] = settings.turso_auth_token
        return args
    if url.startswith("sqlite"):
        # FastAPI runs sync handlers in a threadpool.
        return {"check_same_thread": False}
    return {}


engine = create_engine(settings.database_url, connect_args=_connect_args(), echo=False)


def now_local() -> datetime:
    """Naive local time (Asia/Bangkok by default) for easy day/month grouping."""
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    # "income" | "expense"
    type: str = Field(index=True)
    amount: float
    category: str = Field(default="อื่นๆ", index=True)
    note: str = ""
    raw_message: str = ""
    created_at: NaiveDatetime = Field(default_factory=now_local, index=True)


class ProcessedEvent(SQLModel, table=True):
    """Records LINE webhook event ids we already handled (dedupe redelivery)."""

    __tablename__ = "processed_events"

    event_id: str = Field(primary_key=True)
    created_at: NaiveDatetime = Field(default_factory=now_local, index=True)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def claim_event(event_id: str) -> bool:
    """Atomically claim a webhook event id.

    Returns True the first time an id is seen (safe to process),
    False if it was already handled (duplicate / redelivery).
    """
    if not event_id:
        # No id available -> cannot dedupe, process it.
        return True
    with Session(engine) as session:
        if session.get(ProcessedEvent, event_id) is not None:
            return False
        session.add(ProcessedEvent(event_id=event_id))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return False
    return True


def prune_processed_events(days: int = 7) -> None:
    """Drop old event ids to keep the table small."""
    cutoff = now_local() - timedelta(days=days)
    with Session(engine) as session:
        session.exec(delete(ProcessedEvent).where(ProcessedEvent.created_at < cutoff))
        session.commit()
