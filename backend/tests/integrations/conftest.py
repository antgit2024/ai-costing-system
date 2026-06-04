"""Local pytest fixtures for the integrations test suite.

Independent of ``tests/planner/conftest.py`` so the integrations layer can be
tested without spinning up FastAPI / planner routers.
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.database import Base, configure_engine  # noqa: E402
from src.planner import models as _planner_models  # noqa: E402,F401  - register tables
from src import integrations as _integrations  # noqa: E402,F401  - register clients


def _make_test_db_url() -> tuple[str, Path]:
    db_path = Path(tempfile.gettempdir()) / f"integrations_test_{os.getpid()}_{uuid.uuid4().hex}.db"
    return f"sqlite:///{db_path.as_posix()}", db_path


@pytest.fixture(scope="session")
def engine():
    url, db_path = _make_test_db_url()
    try:
        if db_path.exists():
            db_path.unlink()
    except Exception:
        pass
    eng = configure_engine(url)
    Base.metadata.create_all(bind=eng)
    yield eng
    try:
        eng.dispose()
    finally:
        try:
            if db_path.exists():
                db_path.unlink()
        except Exception:
            pass


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    SessionTesting = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = SessionTesting()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
