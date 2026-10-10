"""Database engine, session, and models."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from pydantic import NaiveDatetime
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


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
