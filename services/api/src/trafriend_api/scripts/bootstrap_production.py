from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional, Sequence

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.models import (
    LeveragedProductRecord,
    UnderlyingRecord,
)
from trafriend_api.settings import Settings

REQUIRED_TABLES = frozenset(
    {
        "alembic_version",
        "daily_close_anchors",
        "underlyings",
        "leveraged_products",
        "market_rankings",
    }
)


@dataclass(frozen=True)
class BootstrapReport:
    revision: str
    underlyings: int
    leveraged_products: int


def inspect_bootstrap(engine: Engine, expected_revision: str) -> BootstrapReport:
    tables = set(inspect(engine).get_table_names())
    missing = REQUIRED_TABLES - tables
    if missing:
        raise ValueError("required production tables are missing")
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
        underlyings = connection.scalar(select(func.count(UnderlyingRecord.id)))
        products = connection.scalar(select(func.count(LeveragedProductRecord.id)))
    if revision != expected_revision:
        raise ValueError("database migration revision is not current")
    if not underlyings or not products:
        raise ValueError("curated leveraged universe metadata is not populated")
    return BootstrapReport(
        revision=revision,
        underlyings=int(underlyings),
        leveraged_products=int(products),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv:
        print("This command does not accept arguments", file=sys.stderr)
        return 1
    engine: Optional[Engine] = None
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, "head")
        expected_revision = ScriptDirectory.from_config(
            alembic_config
        ).get_current_head()
        if expected_revision is None:
            raise ValueError("Alembic has no current migration head")
        engine = create_database_engine(settings.database_url.get_secret_value())
        report = inspect_bootstrap(engine, expected_revision)
        print("Bootstrap Status: READY")
        print(f"Migration Revision: {report.revision}")
        print(f"Underlying Rows: {report.underlyings}")
        print(f"Leveraged Product Rows: {report.leveraged_products}")
        return 0
    except (SQLAlchemyError, ValueError) as exc:
        print(f"Production bootstrap failed: {exc.__class__.__name__}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
