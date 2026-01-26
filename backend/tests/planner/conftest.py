import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import src.compat  # noqa: E402,F401  # ensure ForwardRef patch before FastAPI import
from fastapi.testclient import TestClient  # noqa: E402
from src.database import Base, configure_engine, get_db  # noqa: E402
from src.main import app  # noqa: E402
from src.planner.services import import_service  # noqa: E402
from src.planner import models as _planner_models  # noqa: E402,F401  # ensure all tables are registered

TEST_DATABASE_URL = "sqlite:///./planner_test.db"


@pytest.fixture(scope="session")
def engine():
    engine = configure_engine(TEST_DATABASE_URL)
    # Ensure planner models are imported *before* create_all, otherwise SQLite test DB
    # may miss newly added tables (e.g. shipment_import_batches) and fail at runtime.
    import src.planner.models  # noqa: F401

    # Be defensive: if the sqlite file persists across runs, reset schema to the latest metadata.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


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


@pytest.fixture()
def client(db_session, engine):
    SessionFactory = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    import_service.set_session_factory(SessionFactory)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
