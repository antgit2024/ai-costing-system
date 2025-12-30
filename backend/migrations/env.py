import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from src.config import settings  # noqa: E402
from src.database import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def _ensure_postgres_sslmode(database_url: str) -> str:
    """
    Align alembic migrations with runtime DB behavior.
    Some managed Postgres rejects non-SSL connections ("no encryption").
    If sslmode isn't specified, default to sslmode=require for postgres URLs.
    """
    try:
        url = make_url(database_url)
    except Exception:
        return database_url

    drivername = (url.drivername or "").lower()
    if not (drivername.startswith("postgresql") or drivername.startswith("postgres")):
        return database_url

    query = dict(url.query or {})
    if "sslmode" in query:
        return database_url

    query["sslmode"] = "require"
    return str(url.set(query=query))


def _get_database_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return _ensure_postgres_sslmode(configured_url)
    effective_url = _ensure_postgres_sslmode(settings.database_url)
    config.set_main_option("sqlalchemy.url", effective_url)
    return effective_url


target_metadata = Base.metadata

def run_migrations_offline():
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    _get_database_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
