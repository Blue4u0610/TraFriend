"""Capture completed QQQ-stock daily OHLC independently of Profit Ratio inputs."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.application.services.daily_price import DailyPriceCaptureService
from trafriend_api.domain.errors import MarketDataProviderError, TraFriendDomainError
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.catalog.qqq_constituents import fetch_qqq_constituents
from trafriend_api.infrastructure.catalog.qqq_initialization import ensure_qqq_constituents
from trafriend_api.infrastructure.market_data.alpaca.profit_ratio import (
    AlpacaProfitRatioCaptureProvider,
)
from trafriend_api.infrastructure.persistence.daily_price import PostgreSQLDailyPriceRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.models import UnderlyingRecord
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)
from trafriend_api.settings import Settings


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--refresh-universe", action="store_true")
    arguments = parser.parse_args(argv)
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date()
    end = arguments.end or today
    start = arguments.start or end - timedelta(days=7)
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
        engine = create_database_engine(settings.database_url.get_secret_value())
        catalog = PostgreSQLProfitRatioRepository(engine)
        if arguments.refresh_universe:
            with engine.connect() as connection:
                ids = {
                    row.symbol: row.id
                    for row in connection.execute(
                        select(UnderlyingRecord.symbol, UnderlyingRecord.id)
                    )
                }
            ids.update(
                {member.symbol: member.instrument_id for member in catalog.list_constituents()}
            )
            catalog.save_constituents(fetch_qqq_constituents(instrument_ids=ids))
        constituents = ensure_qqq_constituents(engine)
        provider = AlpacaProfitRatioCaptureProvider(
            key_id=settings.alpaca_key_id.get_secret_value(),
            secret_key=settings.alpaca_secret_key.get_secret_value(),
            instrument_ids={member.symbol: member.instrument_id for member in constituents},
            base_url=settings.alpaca_data_base_url,
        )
        report = DailyPriceCaptureService(
            catalog=catalog,
            repository=PostgreSQLDailyPriceRepository(engine),
            provider=provider,
            calendar=ProfitRatioExchangeCalendar(),
        ).capture(start, end)
        summary = asdict(report)
        summary["results"] = [
            asdict(item) for item in report.results if item.outcome not in {"INSERTED", "EXISTING"}
        ][:25]
        print(
            json.dumps(
                {
                    **summary,
                    "scope": "CURRENT_QQQ_EQUITY_HOLDINGS",
                    "universe_as_of": str(constituents[0].as_of),
                    "universe_source": constituents[0].source,
                    "dataset": "INDEPENDENT_DAILY_PRICE_OHLC",
                    "profit_ratio_required": False,
                    "failure_examples_truncated": report.unavailable + report.conflicts > 25,
                },
                default=str,
            )
        )
        if report.status in {"EMPTY_UNIVERSE", "CONFLICT"}:
            return 1
        return 2 if report.status == "PARTIAL_RETRYABLE" else 0
    except (SQLAlchemyError, ValueError, MarketDataProviderError, TraFriendDomainError) as exc:
        print(json.dumps({"status": "FAILED", "error_class": type(exc).__name__}))
        return 1
    finally:
        if provider is not None:
            provider.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
