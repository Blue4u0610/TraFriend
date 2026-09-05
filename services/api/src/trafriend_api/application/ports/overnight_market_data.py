from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Sequence

from trafriend_api.domain.overnight import (
    HistoricalOvernightBar,
    HistoricalOvernightQuote,
    OvernightBar,
    OvernightQuote,
    OvernightReferenceCapture,
    ProviderCapabilities,
    ReferenceType,
)


class OvernightMarketDataProvider(ABC):
    """Normalized, provider-independent access to true 20:00-04:00 ET data."""

    @property
    @abstractmethod
    def provider_code(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def source_feed(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def get_latest_quotes(self, symbols: Sequence[str]) -> Sequence[OvernightQuote]:
        raise NotImplementedError

    @abstractmethod
    def get_overnight_snapshot(
        self, symbols: Sequence[str], timestamp: datetime
    ) -> Sequence[OvernightQuote]:
        raise NotImplementedError

    @abstractmethod
    def get_overnight_bars(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> Sequence[OvernightBar]:
        raise NotImplementedError


class HistoricalOvernightMarketDataProvider(ABC):
    """Read-only provider port for bounded manual historical diagnostics."""

    @abstractmethod
    def get_historical_overnight_bars(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> Sequence[HistoricalOvernightBar]:
        raise NotImplementedError

    @abstractmethod
    def get_historical_overnight_quotes(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> Sequence[HistoricalOvernightQuote]:
        raise NotImplementedError


class TradingCalendar(ABC):
    @abstractmethod
    def is_trading_day(self, trading_date: date) -> bool:
        raise NotImplementedError


class OvernightReferenceRepository(ABC):
    @abstractmethod
    def save(self, capture: OvernightReferenceCapture) -> OvernightReferenceCapture:
        raise NotImplementedError

    @abstractmethod
    def latest(
        self,
        trading_date: date,
        reference_type: ReferenceType,
        symbols: Sequence[str],
    ) -> OvernightReferenceCapture:
        raise NotImplementedError
