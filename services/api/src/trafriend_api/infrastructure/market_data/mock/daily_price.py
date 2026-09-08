"""Explicit synthetic price candles for credential-free development, not production."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Sequence

from trafriend_api.application.ports.daily_price import DailyPriceProvider
from trafriend_api.domain.daily_price import DailyPriceBar
from trafriend_api.domain.profit_ratio_daily import ProfitRatioSession
from trafriend_api.infrastructure.persistence.daily_price import InMemoryDailyPriceRepository


def mock_daily_price_bars() -> tuple[DailyPriceBar, ...]:
    values = (
        ("NVDA", "168.37", "173", "167.4", "170", "168.37"),
        ("AAPL", "230", "231.2", "226.5", "227.5", "230"),
        ("TSLA", "400", "422.5", "395.2", "420", "400"),
    )
    return tuple(
        DailyPriceBar(
            id=f"mock-daily-{symbol}-2026-09-04",
            instrument_id=f"ins_{symbol.lower()}_xnas",
            symbol=symbol,
            trading_date=date(2026, 9, 4),
            open=Decimal(opening),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(closing),
            previous_close=Decimal(previous),
            session_opened_at=datetime(2026, 9, 4, 13, 30, tzinfo=timezone.utc),
            session_closed_at=datetime(2026, 9, 4, 20, tzinfo=timezone.utc),
            market_timestamp=datetime(2026, 9, 4, 4, tzinfo=timezone.utc),
            observed_at=datetime(2026, 9, 4, 20, 20, tzinfo=timezone.utc),
            provider="mock",
            source_feed="MOCK_NASDAQ_FIXTURE",
            quality="MOCK",
        )
        for symbol, opening, high, low, closing, previous in values
    )


class MockDailyPriceProvider(DailyPriceProvider):
    def __init__(self, bars: Sequence[DailyPriceBar] = ()) -> None:
        self._bars = tuple(bars) if bars else mock_daily_price_bars()

    def get_daily_price_bars(
        self, symbols: Sequence[str], sessions: Sequence[ProfitRatioSession]
    ) -> tuple[DailyPriceBar, ...]:
        dates = {session.trading_date for session in sessions}
        return tuple(
            bar for bar in self._bars if bar.symbol in symbols and bar.trading_date in dates
        )


def build_mock_daily_price_repository() -> InMemoryDailyPriceRepository:
    return InMemoryDailyPriceRepository(mock_daily_price_bars())
