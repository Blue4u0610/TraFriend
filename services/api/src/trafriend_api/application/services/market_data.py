from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Sequence

from trafriend_api.application.ports.market_data import MarketDataProvider
from trafriend_api.domain.calculator import calculate_theoretical_target
from trafriend_api.domain.errors import (
    ReferenceUnavailableError,
    ReferenceVersionInactiveError,
)
from trafriend_api.domain.models import (
    CalculationResult,
    DailyReferenceSet,
    Instrument,
    LeveragedRelationship,
    ProfitRatioHistory,
)


class MarketDataService:
    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    @property
    def provider_code(self) -> str:
        return self._provider.provider_code

    def search_instruments(self, query: str, limit: int = 10) -> Sequence[Instrument]:
        return self._provider.search_instruments(query=query, limit=limit)

    def get_instrument(self, instrument_id: str) -> Instrument:
        return self._provider.get_instrument(instrument_id)

    def get_leveraged_relationships(
        self, instrument_id: str
    ) -> Sequence[LeveragedRelationship]:
        return self._provider.get_leveraged_relationships(instrument_id)

    def get_relationship(self, relationship_id: str) -> LeveragedRelationship:
        return self._provider.get_relationship(relationship_id)

    def get_reference(self, relationship_id: str) -> DailyReferenceSet:
        return self._provider.get_reference(relationship_id)

    def calculate(
        self,
        relationship_id: str,
        reference_version_id: str,
        input_side: str,
        target_price: Decimal,
    ) -> CalculationResult:
        relationship = self._provider.get_relationship(relationship_id)
        reference = self._provider.get_reference(relationship_id)
        if reference.id != reference_version_id or reference.status != "active":
            raise ReferenceVersionInactiveError(
                "the submitted Daily Reference Price version is no longer active"
            )
        if reference.freshness != "current":
            raise ReferenceUnavailableError(
                "the Daily Reference Price set is not current enough for calculation"
            )
        return calculate_theoretical_target(
            relationship=relationship,
            reference=reference,
            input_side=input_side,
            target_price=target_price,
        )

    def get_profit_ratio_history(
        self, instrument_id: str, start: date, end: date
    ) -> ProfitRatioHistory:
        return self._provider.get_profit_ratio_history(instrument_id, start, end)
