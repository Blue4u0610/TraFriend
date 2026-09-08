from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Sequence

from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioCaptureInput,
    ProfitRatioPhase,
    ProfitRatioRecord,
    ProfitRatioSession,
)


class ProfitRatioPersistenceOutcome(str, Enum):
    INSERTED = "INSERTED"
    EXISTING = "EXISTING"
    UPGRADED = "UPGRADED"


@dataclass(frozen=True)
class ProfitRatioPersistenceResult:
    record: ProfitRatioRecord
    outcome: ProfitRatioPersistenceOutcome


class ProfitRatioRepository(ABC):
    @abstractmethod
    def list_constituents(self) -> Sequence[NasdaqConstituent]:
        raise NotImplementedError

    @abstractmethod
    def save_constituents(self, constituents: Sequence[NasdaqConstituent]) -> None:
        """Replace the current sourced membership snapshot, retaining observations."""
        raise NotImplementedError

    @abstractmethod
    def latest(
        self, instrument_id: str, trading_date: date, phase: ProfitRatioPhase
    ) -> Optional[ProfitRatioRecord]:
        raise NotImplementedError

    @abstractmethod
    def history(self, instrument_id: str, start: date, end: date) -> Sequence[ProfitRatioRecord]:
        """Latest immutable version for each date/phase, never gap filling."""
        raise NotImplementedError

    @abstractmethod
    def save(self, record: ProfitRatioRecord) -> ProfitRatioPersistenceResult:
        """Atomically store ratio and separate price; upgrade null via a new version only."""
        raise NotImplementedError


class ProfitRatioCaptureProvider(ABC):
    @abstractmethod
    def get_capture_inputs(
        self, symbols: Sequence[str], session: ProfitRatioSession, phase: ProfitRatioPhase
    ) -> Sequence[ProfitRatioCaptureInput]:
        raise NotImplementedError


class ProfitRatioSessionCalendar(ABC):
    @abstractmethod
    def session(self, trading_date: date) -> ProfitRatioSession:
        raise NotImplementedError

    @abstractmethod
    def sessions(self, start: date, end: date) -> Sequence[ProfitRatioSession]:
        raise NotImplementedError
