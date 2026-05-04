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

import src.compat  # noqa: E402,F401  # ensure ForwardRef patch before FastAPI import
from fastapi.testclient import TestClient  # noqa: E402
from src.database import Base, configure_engine, get_db  # noqa: E402
from src.main import app  # noqa: E402
from src.planner.dependencies import require_staff_role  # noqa: E402
from src.planner.services import import_service  # noqa: E402
from src.planner import models as _planner_models  # noqa: E402,F401  # ensure all tables are registered

def _make_test_db_url() -> tuple[str, Path]:
    """
    Use an absolute sqlite file under /tmp for test stability.

    Rationale:
    - Some CI/runner environments mount the repo workspace with restrictive semantics that can
      intermittently trigger "attempt to write a readonly database" for sqlite file DBs.
    - /tmp is the safest location for ephemeral test DBs.
    """

    db_path = Path(tempfile.gettempdir()) / f"planner_test_{os.getpid()}_{uuid.uuid4().hex}.db"
    # sqlite URL format for absolute path: sqlite:////tmp/xxx.db
    return f"sqlite:///{db_path.as_posix()}", db_path


@pytest.fixture(scope="session")
def engine():
    test_db_url, db_path = _make_test_db_url()
    try:
        if db_path.exists():
            db_path.unlink()
    except Exception:
        # best-effort cleanup; tests will still attempt create_all
        pass

    engine = configure_engine(test_db_url)
    # Ensure planner models are imported *before* create_all, otherwise SQLite test DB
    # may miss newly added tables (e.g. shipment_import_batches) and fail at runtime.
    import src.planner.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield engine
    try:
        engine.dispose()
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
    # COSTING-C1: 默认 override staff 守卫 · 等价"服务账号"身份(payload=None)·
    # 单独测 require_staff_role 行为时再用专用 fixture 覆盖。
    app.dependency_overrides[require_staff_role] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
