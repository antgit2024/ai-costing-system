from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_creates_tables(tmp_path):
    db_path = tmp_path / "migration.sqlite"
    database_url = f"sqlite:///{db_path}"

    backend_root = Path(__file__).resolve().parents[2]
    config_path = backend_root / "alembic.ini"
    alembic_cfg = Config(str(config_path))
    alembic_cfg.set_main_option("script_location", str(backend_root / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_cfg, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected_tables = {
        "cost_initiatives",
        "cost_packages",
        "cost_line_items",
        "supplier_quotes",
        "input_assumptions",
        "scenario_versions",
        "scenario_line_snapshots",
        "approval_records",
        "attachments",
        "planner_import_jobs",
    }
    for table in expected_tables:
        assert table in tables
