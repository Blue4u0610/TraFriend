from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Sequence

from trafriend_api.domain.universe import (
    MarketRanking,
    PopularDataset,
    RankingAsset,
    RankingDailyBar,
    RankingType,
)


class MarketRankingRepository(ABC):
    @abstractmethod
    def get_dataset(
        self, ranking_period: str, ranking_type: RankingType, limit: int = 100
    ) -> PopularDataset:
        raise NotImplementedError

    @abstractmethod
    def replace_verified_rows(self, rows: Sequence[MarketRanking]) -> int:
        """Atomically replace one verified period/type dataset."""
        raise NotImplementedError


class RankingMarketDataProvider(ABC):
    @property
    @abstractmethod
    def provider_code(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def source_feed(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def list_active_us_equities(self) -> Sequence[RankingAsset]:
        raise NotImplementedError

    @abstractmethod
    def get_daily_ranking_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[RankingDailyBar]:
        raise NotImplementedError


class RankingSessionCalendar(ABC):
    @abstractmethod
    def completed_trading_dates_in_month(
        self, timestamp: datetime, year: int, month: int
    ) -> Sequence[date]:
        raise NotImplementedError
