from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

import httpx
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.models import (
    DailyCloseAnchorRecord,
    LeveragedProductRecord,
    MarketRankingRecord,
    UnderlyingRecord,
)
from trafriend_api.scripts.bootstrap_production import REQUIRED_TABLES

UTC = timezone.utc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run non-destructive deployment checks without printing secrets."
    )
    parser.add_argument(
        "--api-url",
        help="Optional deployed API origin whose /health endpoint should be checked.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    required = ("DATABASE_URL", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    available = {name: bool(os.getenv(name)) for name in required}
    for name in required:
        print(f"{name}: {'SET' if available[name] else 'MISSING'}")
    if not available["DATABASE_URL"]:
        return 1

    engine = None
    try:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
            revision = MigrationContext.configure(connection).get_current_revision()
            tables = set(inspect(connection).get_table_names())
            if not REQUIRED_TABLES.issubset(tables):
                raise ValueError("required tables are missing")
            expected = ScriptDirectory.from_config(
                Config("alembic.ini")
            ).get_current_head()
            if revision != expected:
                raise ValueError("migration is not at head")
            underlying_count = int(
                connection.scalar(select(func.count(UnderlyingRecord.id))) or 0
            )
            product_count = int(
                connection.scalar(select(func.count(LeveragedProductRecord.id))) or 0
            )
            ranking_count = int(
                connection.scalar(select(func.count(MarketRankingRecord.rank))) or 0
            )
            anchor_count = int(
                connection.scalar(select(func.count(DailyCloseAnchorRecord.id))) or 0
            )
            latest_anchor = connection.scalar(
                select(func.max(DailyCloseAnchorRecord.trading_date))
            )
        session = NyseTradingCalendar().latest_completed_session(datetime.now(UTC))
        print("Database Connection: SUCCESS")
        print(f"Migration Revision: {revision}")
        print("Required Tables: PRESENT")
        print(f"Underlying Rows: {underlying_count}")
        print(f"Leveraged Product Rows: {product_count}")
        print(f"Ranking Rows: {ranking_count}")
        print(f"Daily Close Anchor Rows: {anchor_count}")
        print(f"Expected Trading Date: {session.trading_date.isoformat()}")
        print(f"Latest Anchor Trading Date: {latest_anchor or 'NONE'}")
    except (SQLAlchemyError, ValueError):
        print("Database Validation: FAILED", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    if args.api_url:
        try:
            response = httpx.get(
                f"{args.api_url.rstrip('/')}/health",
                timeout=10,
                follow_redirects=False,
            )
            if response.status_code != 200:
                raise ValueError("health endpoint did not return HTTP 200")
            print("API Health: PASS")
        except (httpx.HTTPError, ValueError):
            print("API Health: FAIL", file=sys.stderr)
            return 1
    else:
        print("API Health: NOT CHECKED (provide --api-url after deployment)")
    return 0 if all(available.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
