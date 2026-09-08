from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Sequence

from trafriend_api.domain.daily_price import DailyPriceBar
from trafriend_api.domain.profit_ratio_daily import ProfitRatioSession


class DailyPricePersistenceOutcome(str, Enum):
    INSERTED = "INSERTED"
    EXISTING = "EXISTING"


@dataclass(frozen=True)
class DailyPricePersistenceResult:
    bar: DailyPriceBar
    outcome: DailyPricePersistenceOutcome


class DailyPriceRepository(ABC):
    @abstractmethod
    def get(self, instrument_id: str, trading_date: date) -> Optional[DailyPriceBar]:
        raise NotImplementedError

    @abstractmethod
    def history(self, instrument_id: str, start: date, end: date) -> Sequence[DailyPriceBar]:
        raise NotImplementedError

    @abstractmethod
    def save(self, bar: DailyPriceBar) -> DailyPricePersistenceResult:
        raise NotImplementedError


class DailyPriceProvider(ABC):
    @abstractmethod
    def get_daily_price_bars(
        self, symbols: Sequence[str], sessions: Sequence[ProfitRatioSession]
    ) -> Sequence[DailyPriceBar]:
        """Batch completed daily OHLC, keeping absent symbols/dates absent."""
        raise NotImplementedError
