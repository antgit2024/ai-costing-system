from __future__ import annotations

from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

Base = declarative_base()
engine = None
SessionLocal = None


def _build_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        database_url,
        echo=False,
        future=True,
        connect_args=connect_args,
    )


def configure_engine(database_url: Optional[str] = None):
    """Configure engine + session factory. Useful for tests overriding DB."""

    global engine, SessionLocal
    target_url = database_url or settings.database_url
    engine = _build_engine(target_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_db() -> Generator:
    """FastAPI dependency that provides a database session."""

    if SessionLocal is None:
        configure_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# initialize engine on import
configure_engine()
