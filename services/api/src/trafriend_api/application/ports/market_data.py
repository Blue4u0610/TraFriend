from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Sequence

from trafriend_api.domain.models import (
    Instrument,
    LeveragedRelationship,
    ProfitRatioHistory,
)


class LeveragedRelationshipCatalog(ABC):
    """Curated relationship metadata independent of market-price providers."""

    @abstractmethod
    def search_instruments(self, query: str, limit: int) -> Sequence[Instrument]:
        raise NotImplementedError

    @abstractmethod
    def search_underlyings(self, query: str, limit: int) -> Sequence[Instrument]:
        """Search only supported underlying instruments using local metadata."""
        raise NotImplementedError

    @abstractmethod
    def search_leveraged_products(
        self, query: str, limit: int
    ) -> Sequence[Instrument]:
        """Search only verified leveraged products using local metadata."""
        raise NotImplementedError

    @abstractmethod
    def get_instrument(self, instrument_id: str) -> Instrument:
        raise NotImplementedError

    @abstractmethod
    def get_instrument_by_symbol(self, symbol: str) -> Instrument:
        raise NotImplementedError

    @abstractmethod
    def get_leveraged_relationships(
        self, instrument_id: str
    ) -> Sequence[LeveragedRelationship]:
        raise NotImplementedError

    @abstractmethod
    def list_underlyings(self) -> Sequence[Instrument]:
        raise NotImplementedError

    @abstractmethod
    def get_relationship(self, relationship_id: str) -> LeveragedRelationship:
        raise NotImplementedError


class MarketDataProvider(ABC):
    """Normalized capabilities needed by Phase 1 market-data use cases."""

    @property
    @abstractmethod
    def provider_code(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_profit_ratio_history(
        self, instrument_id: str, start: date, end: date
    ) -> ProfitRatioHistory:
        raise NotImplementedError
