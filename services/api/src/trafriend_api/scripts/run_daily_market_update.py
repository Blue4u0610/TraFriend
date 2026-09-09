from __future__ import annotations

import sys
from typing import Optional, Sequence

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.application.services.daily_price import DailyPriceCaptureService
from trafriend_api.application.services.market_update import DailyMarketUpdateService
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.catalog.qqq_initialization import ensure_qqq_constituents
from trafriend_api.infrastructure.market_data.alpaca.profit_ratio import (
    AlpacaProfitRatioCaptureProvider,
)
from trafriend_api.infrastructure.persistence import PostgreSQLMarketRankingRepository
from trafriend_api.infrastructure.persistence.daily_price import PostgreSQLDailyPriceRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.database_target import (
    require_writable_database_target,
)
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)
from trafriend_api.presentation.http.dependencies import build_application_services
from trafriend_api.scripts.calculate_mtd_rankings import build_ranking_service
from trafriend_api.settings import Settings


def _exit_code_for_status(status: str) -> int:
    if status in {"COMPLETE", "SKIPPED"}:
        return 0
    return 2 if status == "PARTIAL_RETRYABLE" else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv:
        print("This command does not accept arguments", file=sys.stderr)
        return 1
    engine: Optional[Engine] = None
    ohlc_provider: Optional[AlpacaProfitRatioCaptureProvider] = None
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
            raise ValueError("Alpaca credentials are required")
        database_url = settings.database_url.get_secret_value()
        alpaca_key_id = settings.alpaca_key_id.get_secret_value()
        alpaca_secret_key = settings.alpaca_secret_key.get_secret_value()
        target = require_writable_database_target(database_url, settings.environment)
        settings = settings.model_copy(update={"daily_close_provider": "alpaca"})
        engine = create_database_engine(database_url)
        calendar = NyseTradingCalendar()
        constituents = ensure_qqq_constituents(engine)
        qqq_catalog = PostgreSQLProfitRatioRepository(engine)
        ohlc_provider = AlpacaProfitRatioCaptureProvider(
            key_id=alpaca_key_id,
            secret_key=alpaca_secret_key,
            instrument_ids={
                member.symbol: member.instrument_id for member in constituents
            },
            base_url=settings.alpaca_data_base_url,
        )
        report = DailyMarketUpdateService(
            calendar=calendar,
            ranking_repository=PostgreSQLMarketRankingRepository(engine),
            ranking_builder=build_ranking_service(settings, engine, calendar),
            daily_close_capture=build_application_services(
                settings, database_engine=engine
            ).universe,
            daily_ohlc_capture=DailyPriceCaptureService(
                catalog=qqq_catalog,
                repository=PostgreSQLDailyPriceRepository(engine),
                provider=ohlc_provider,
                calendar=ProfitRatioExchangeCalendar(),
            ),
        ).run()
        print(f"Data Target: {target.environment.value}")
        print(f"Database Host: {target.host}")
        print(f"Database Name: {target.database}")
        print(f"Daily Market Update: {report.status}")
        print(f"Latest Completed Trading Date: {report.trading_date}")
        print(f"Ranking Period: {report.ranking_period}")
        print(f"Ranking: {report.ranking_status}")
        print(f"Ranking Rows: {report.ranking_rows}")
        print(f"Daily Close: {report.daily_close_status}")
        close_report = report.daily_close_report
        print(f"Inserted: {close_report.inserted if close_report else 0}")
        print(f"Existing: {close_report.existing if close_report else 0}")
        print(
            "Skipped No Supported Product: "
            f"{close_report.skipped_no_supported_product if close_report else 0}"
        )
        print(f"Unavailable: {close_report.unavailable if close_report else 0}")
        print(f"Conflicts: {close_report.conflicts if close_report else 0}")
        ohlc_report = report.ohlc_report
        complete_ohlc = (
            ohlc_report.inserted + ohlc_report.existing if ohlc_report else 0
        )
        print(f"OHLC: {report.ohlc_status}")
        print(f"OHLC Open Values: {complete_ohlc}")
        print(f"OHLC Close Values: {complete_ohlc}")
        print(f"OHLC Inserted: {ohlc_report.inserted if ohlc_report else 0}")
        print(f"OHLC Existing: {ohlc_report.existing if ohlc_report else 0}")
        print(f"OHLC Unavailable: {ohlc_report.unavailable if ohlc_report else 0}")
        print(f"OHLC Conflicts: {ohlc_report.conflicts if ohlc_report else 0}")
        return _exit_code_for_status(report.status)
    except (SQLAlchemyError, ValueError) as exc:
        print(
            f"Daily market update failed: {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 1
    finally:
        if ohlc_provider is not None:
            ohlc_provider.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
