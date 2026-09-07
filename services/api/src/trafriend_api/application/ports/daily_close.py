from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Sequence

from trafriend_api.domain.daily_close import (
    CompletedTradingSession,
    DailyCloseAnchor,
    DailyCloseBar,
)


class DailyCloseMarketDataProvider(ABC):
    """Normalized access to completed regular-session daily bars."""

    @property
    @abstractmethod
    def provider_code(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def daily_close_feed(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_daily_close_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[DailyCloseBar]:
        raise NotImplementedError


class CompletedSessionCalendar(ABC):
    @abstractmethod
    def latest_completed_session(
        self, timestamp: datetime
    ) -> CompletedTradingSession:
        raise NotImplementedError


class AnchorPersistenceOutcome(str, Enum):
    INSERTED = "INSERTED"
    EXISTING = "EXISTING"
    NOT_PERSISTED = "NOT_PERSISTED"


@dataclass(frozen=True)
class DailyCloseAnchorPersistenceResult:
    anchor: DailyCloseAnchor
    outcome: AnchorPersistenceOutcome


class DailyCloseAnchorRepository(ABC):
    @abstractmethod
    def save(
        self, anchor: DailyCloseAnchor
    ) -> DailyCloseAnchorPersistenceResult:
        raise NotImplementedError

    @abstractmethod
    def latest(self, relationship_id: str) -> DailyCloseAnchor:
        raise NotImplementedError
