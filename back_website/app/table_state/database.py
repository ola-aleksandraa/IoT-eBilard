"""Engine/session setup. One Database per application instance (tests use in-memory SQLite)."""

import os
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Production example: mysql+pymysql://bilard:secret@127.0.0.1:3306/bilard
# Without DATABASE_URL a local SQLite file is used, so development needs no MySQL server.
DEFAULT_DATABASE_URL = "sqlite:///./table_state.db"


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Database:
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        kwargs: dict = {"pool_pre_ping": True}
        if self.url.startswith("sqlite"):
            # The watcher thread and request threads share the engine.
            kwargs["connect_args"] = {"check_same_thread": False}
            if self.url in ("sqlite://", "sqlite:///:memory:"):
                kwargs["poolclass"] = StaticPool  # one shared in-memory database
        self.engine = create_engine(self.url, **kwargs)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_schema(self) -> None:
        from . import models  # noqa: F401  (registers the tables)
        Base.metadata.create_all(self.engine)  # use Alembic migrations in production

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = request.app.state.db.session_factory()
    try:
        yield db
    finally:
        db.close()
