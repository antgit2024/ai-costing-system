from __future__ import annotations

from typing import Generator, Optional

from sqlalchemy import create_engine
import os

from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

Base = declarative_base()
engine = None
SessionLocal = None


def _ensure_postgres_sslmode(database_url: str) -> str:
    """
    Production guardrail:
    Some environments require SSL ("no encryption"), while some proxies/endpoints do not
    support SSL ("server does not support SSL").
    If caller didn't specify sslmode in URL, default to sslmode=require for postgres URLs.
    You can override via env: PLANNER_PG_SSLMODE (e.g. require/verify-full/disable).
    """
    try:
        url = make_url(database_url)
    except Exception:
        return database_url

    drivername = (url.drivername or "").lower()
    if not (drivername.startswith("postgresql") or drivername.startswith("postgres")):
        return database_url

    query = dict(url.query or {})
    forced = (os.getenv("PLANNER_PG_SSLMODE") or "").strip()
    # If env is set, force override even when URL already has sslmode.
    if forced:
        query["sslmode"] = forced
        return str(url.set(query=query))

    if "sslmode" in query:
        return database_url

    query["sslmode"] = "require"
    return str(url.set(query=query))


def _build_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    database_url = _ensure_postgres_sslmode(database_url)
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
