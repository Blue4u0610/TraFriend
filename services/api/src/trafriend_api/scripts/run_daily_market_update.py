from __future__ import annotations

import sys
from typing import Optional, Sequence

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.application.services.market_update import DailyMarketUpdateService
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.persistence import PostgreSQLMarketRankingRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.presentation.http.dependencies import build_application_services
from trafriend_api.scripts.calculate_mtd_rankings import build_ranking_service
from trafriend_api.settings import Settings


def _exit_code_for_status(status: str) -> int:
    return 0 if status in {"COMPLETE", "SKIPPED"} else 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv:
        print("This command does not accept arguments", file=sys.stderr)
        return 1
    engine: Optional[Engine] = None
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
            raise ValueError("Alpaca credentials are required")
        database_url = settings.database_url.get_secret_value()
        settings = settings.model_copy(update={"daily_close_provider": "alpaca"})
        engine = create_database_engine(database_url)
        calendar = NyseTradingCalendar()
        report = DailyMarketUpdateService(
            calendar=calendar,
            ranking_repository=PostgreSQLMarketRankingRepository(engine),
            ranking_builder=build_ranking_service(settings, engine, calendar),
            daily_close_capture=build_application_services(settings).universe,
        ).run()
        print(f"Daily Market Update: {report.status}")
        print(f"Latest Completed Trading Date: {report.trading_date}")
        print(f"Ranking Period: {report.ranking_period}")
        print(f"Ranking: {report.ranking_status}")
        print(f"Ranking Rows: {report.ranking_rows}")
        print(f"Daily Close: {report.daily_close_status}")
        print(f"Inserted: {report.daily_close_report.inserted}")
        print(f"Existing: {report.daily_close_report.existing}")
        print(
            "Skipped No Supported Product: "
            f"{report.daily_close_report.skipped_no_supported_product}"
        )
        print(f"Unavailable: {report.daily_close_report.unavailable}")
        print(f"Conflicts: {report.daily_close_report.conflicts}")
        return _exit_code_for_status(report.status)
    except (SQLAlchemyError, ValueError) as exc:
        print(
            f"Daily market update failed: {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
