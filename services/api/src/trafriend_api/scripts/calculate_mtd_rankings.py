from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.application.services.ranking import MarketRankingService
from trafriend_api.domain.errors import MarketDataProviderError
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.catalog import PostgreSQLLeveragedUniverseRepository
from trafriend_api.infrastructure.market_data.alpaca import AlpacaRankingDataProvider
from trafriend_api.infrastructure.persistence import PostgreSQLMarketRankingRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.settings import Settings

UTC = timezone.utc
PERIOD_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate and persist the current verified MTD dollar-volume ranking."
    )
    parser.add_argument(
        "--period",
        help="Optional YYYY-MM period; defaults to the latest completed NYSE session month.",
    )
    return parser


def parse_period(value: str) -> tuple[int, int]:
    match = PERIOD_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError("ranking period must use YYYY-MM")
    year, month = int(match.group(1)), int(match.group(2))
    if month < 1 or month > 12:
        raise ValueError("ranking period month must be between 01 and 12")
    return year, month


def build_ranking_service(
    settings: Settings,
    engine: Engine,
    calendar: NyseTradingCalendar,
) -> MarketRankingService:
    if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
        raise ValueError("Alpaca credentials are required")
    return MarketRankingService(
        provider=AlpacaRankingDataProvider(
            key_id=settings.alpaca_key_id.get_secret_value(),
            secret_key=settings.alpaca_secret_key.get_secret_value(),
            trading_base_url=settings.alpaca_trading_base_url,
            data_base_url=settings.alpaca_data_base_url,
            feed=settings.alpaca_daily_bars_feed,
        ),
        calendar=calendar,
        repository=PostgreSQLMarketRankingRepository(engine),
        catalog=PostgreSQLLeveragedUniverseRepository(engine),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    engine: Optional[Engine] = None
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        calendar = NyseTradingCalendar()
        if args.period:
            year, month = parse_period(args.period)
        else:
            session = calendar.latest_completed_session(datetime.now(UTC))
            year, month = session.trading_date.year, session.trading_date.month
        engine = create_database_engine(settings.database_url.get_secret_value())
        report = build_ranking_service(settings, engine, calendar).build_month_to_date(
            year, month
        )
        print(f"Dataset Status: {report.rows[0].period_status.value}")
        print(f"Ranking Period: {report.ranking_period}")
        print(
            "Completed Trading Dates: "
            + ",".join(item.isoformat() for item in report.completed_trading_dates)
        )
        print(f"Candidate Symbols Processed: {report.candidate_assets}")
        print(f"Complete Candidate Symbols: {report.complete_assets}")
        print(f"Incomplete Candidate Symbols: {report.incomplete_assets}")
        print("Ranking Formula: SUM(daily VWAP * daily share volume)")
        print(f"Top100 Rows Persisted: {report.persisted_rows}")
        return 0
    except (MarketDataProviderError, SQLAlchemyError, ValueError) as exc:
        print(
            f"MTD ranking calculation failed: {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
