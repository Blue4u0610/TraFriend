from __future__ import annotations

import sys
from typing import Optional, Sequence

from trafriend_api.application.services.ranking import MarketRankingService
from trafriend_api.domain.errors import MarketDataProviderError
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.catalog import PostgreSQLLeveragedUniverseRepository
from trafriend_api.infrastructure.market_data.alpaca import AlpacaRankingDataProvider
from trafriend_api.infrastructure.persistence import PostgreSQLMarketRankingRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.settings import Settings


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv:
        print("This command does not accept positional arguments", file=sys.stderr)
        return 1
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
            raise ValueError("Alpaca credentials are required")
        engine = create_database_engine(settings.database_url.get_secret_value())
        service = MarketRankingService(
            provider=AlpacaRankingDataProvider(
                key_id=settings.alpaca_key_id.get_secret_value(),
                secret_key=settings.alpaca_secret_key.get_secret_value(),
                trading_base_url=settings.alpaca_trading_base_url,
                data_base_url=settings.alpaca_data_base_url,
                feed=settings.alpaca_daily_bars_feed,
            ),
            calendar=NyseTradingCalendar(),
            repository=PostgreSQLMarketRankingRepository(engine),
            catalog=PostgreSQLLeveragedUniverseRepository(engine),
        )
        report = service.build_september_2026()
        engine.dispose()
        print(f"Dataset Status: {report.rows[0].period_status.value}")
        print(
            "Completed Trading Dates: "
            + ",".join(item.isoformat() for item in report.completed_trading_dates)
        )
        print(f"Candidate Symbols Processed: {report.candidate_assets}")
        print(f"Complete Candidate Symbols: {report.complete_assets}")
        print(f"Incomplete Candidate Symbols: {report.incomplete_assets}")
        print("Ranking Formula: SUM(daily VWAP * daily share volume)")
        print(f"Top100 Rows Persisted: {report.persisted_rows}")
        for row in report.rows[:10]:
            print(
                f"{row.rank}. {row.symbol} — {row.display_name} — "
                f"{row.trading_metric}"
            )
        return 0
    except (MarketDataProviderError, ValueError) as exc:
        print(f"September ranking calculation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
