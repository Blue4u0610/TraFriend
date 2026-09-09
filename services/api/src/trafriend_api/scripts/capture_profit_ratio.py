"""Finite, idempotent QQQ OPEN/CLOSE capture; safe for an external scheduler."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.application.ports.profit_ratio import ProfitRatioRepository
from trafriend_api.application.services.daily_price import DailyPriceCaptureService
from trafriend_api.application.services.profit_ratio import ProfitRatioService
from trafriend_api.domain.errors import MarketDataProviderError
from trafriend_api.domain.profit_ratio_daily import ProfitRatioConflictError, ProfitRatioPhase
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.catalog.qqq_constituents import fetch_qqq_constituents
from trafriend_api.infrastructure.market_data.alpaca.profit_ratio import (
    AlpacaProfitRatioCaptureProvider,
)
from trafriend_api.infrastructure.persistence.daily_price import PostgreSQLDailyPriceRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.database_target import (
    require_writable_database_target,
)
from trafriend_api.infrastructure.persistence.models import UnderlyingRecord
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)
from trafriend_api.settings import Settings


def exit_code(statuses: Sequence[str]) -> int:
    if any(status in {"CONFLICT", "EMPTY_UNIVERSE"} for status in statuses):
        return 1
    if "PARTIAL_RETRYABLE" in statuses:
        return 2
    # Missing model prerequisites need operator action, not endless provider retries.
    # The report continues to say DATA_INSUFFICIENT, never COMPLETE ratios.
    return 0


def _refresh_universe(
    repository: ProfitRatioRepository, catalog_ids: Mapping[str, str]
) -> None:
    ids = dict(catalog_ids)
    # Once observations use a QQQ identity, later leveraged-catalog additions must
    # not re-key that symbol and disconnect its immutable historical records.
    ids.update({item.symbol: item.instrument_id for item in repository.list_constituents()})
    repository.save_constituents(fetch_qqq_constituents(instrument_ids=ids))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--refresh-universe", action="store_true")
    parser.add_argument("--retry-insufficient", action="store_true")
    arguments = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    end = arguments.end or today
    # A scheduler run catches up a bounded recent window after downtime. Historical
    # replay is explicit and reports today's membership, not past index membership.
    start = arguments.start or max(date(2026, 9, 8), end - timedelta(days=7))
    if end < start or (end - start).days > 100 or end > today:
        parser.error("use an ordered past/current range of at most 100 days")
    engine = None
    provider = None
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
            raise ValueError("Alpaca credentials are required")
        database_url = settings.database_url.get_secret_value()
        target = require_writable_database_target(database_url, settings.environment)
        engine = create_database_engine(database_url)
        repository = PostgreSQLProfitRatioRepository(engine)
        if arguments.refresh_universe:
            with engine.connect() as connection:
                ids = {
                    row.symbol: row.id
                    for row in connection.execute(
                        select(UnderlyingRecord.symbol, UnderlyingRecord.id)
                    )
                }
            _refresh_universe(repository, ids)
        constituents = repository.list_constituents()
        if not constituents:
            raise ValueError("QQQ membership is empty; explicitly refresh the issuer snapshot")
        provider = AlpacaProfitRatioCaptureProvider(
            key_id=settings.alpaca_key_id.get_secret_value(),
            secret_key=settings.alpaca_secret_key.get_secret_value(),
            instrument_ids={item.symbol: item.instrument_id for item in constituents},
            base_url=settings.alpaca_data_base_url,
        )
        calendar = ProfitRatioExchangeCalendar()
        sessions = calendar.sessions(start, end)
        ratio_prefetch_failed = False
        if (
            sessions
            and end < today
            and any(
                repository.latest(item.instrument_id, session.trading_date, phase) is None
                for session in sessions
                for item in constituents
                for phase in ProfitRatioPhase
            )
        ):
            try:
                provider.prime_history(
                    [item.symbol for item in constituents], sessions[0].previous_trading_date, end
                )
            except MarketDataProviderError:
                # Report missing ratio inputs per phase without repeating a failed
                # batch for every day, and still attempt independent price capture.
                ratio_prefetch_failed = True
        service = ProfitRatioService(
            repository, calendar, None if ratio_prefetch_failed else provider
        )
        reports = [
            service.capture(
                session.trading_date, phase, retry_insufficient=arguments.retry_insufficient
            )
            for session in sessions
            for phase in ProfitRatioPhase
        ]
        # The existing external OPEN/CLOSE runner also maintains completed price
        # candles. Missing ratio prerequisites must not suppress independent OHLC.
        price_report = DailyPriceCaptureService(
            repository, PostgreSQLDailyPriceRepository(engine), provider, calendar
        ).capture(start, end)
        statuses = [report.status for report in reports] + [price_report.status]
        print(
            json.dumps(
                {
                    "universe_source": constituents[0].source,
                    "universe_as_of": str(constituents[0].as_of),
                    "symbols": len(constituents),
                    "data_target": target.environment.value,
                    "database_host": target.host,
                    "database_name": target.database,
                    "scope": "CURRENT_QQQ_EQUITY_HOLDINGS",
                    "start": str(start),
                    "end": str(end),
                    "status": "PARTIAL_RETRYABLE"
                    if "PARTIAL_RETRYABLE" in statuses
                    else "CONFLICT"
                    if "CONFLICT" in statuses
                    else "DATA_INSUFFICIENT"
                    if "DATA_INSUFFICIENT" in statuses
                    else "NOT_DUE"
                    if not reports or all(s == "NOT_DUE" for s in statuses)
                    else "COMPLETE",
                    "inserted": sum(report.inserted for report in reports),
                    "existing": sum(report.existing for report in reports),
                    "data_insufficient": sum(report.data_insufficient for report in reports),
                    "unavailable": sum(report.unavailable for report in reports),
                    "conflicts": sum(report.conflicts for report in reports),
                    "reports": [asdict(report) for report in reports],
                    "daily_prices": asdict(price_report),
                },
                default=str,
            )
        )
        return exit_code(statuses)
    except (SQLAlchemyError, ValueError, MarketDataProviderError, ProfitRatioConflictError) as exc:
        # Never log DSNs, usernames, HTTP payloads, or credential-bearing exceptions.
        print(json.dumps({"status": "FAILED", "error_class": type(exc).__name__}))
        return 1
    finally:
        if provider is not None:
            provider.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
