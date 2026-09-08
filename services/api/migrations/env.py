from __future__ import annotations

import os
from logging.config import fileConfig
from typing import Optional

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

from trafriend_api.infrastructure.persistence.database import normalize_database_url
from trafriend_api.infrastructure.persistence.models import Base
from trafriend_api.infrastructure.persistence import daily_price_models, profit_ratio_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for Alembic migrations")
    try:
        return normalize_database_url(database_url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online(connection: Optional[Connection] = None) -> None:
    if connection is not None:
        _run_with_connection(connection)
        return

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as created_connection:
        _run_with_connection(created_connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online(config.attributes.get("connection"))
