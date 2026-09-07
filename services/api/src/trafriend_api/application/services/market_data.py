from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Sequence

from trafriend_api.application.ports.market_data import (
    LeveragedRelationshipCatalog,
    MarketDataProvider,
)
from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.domain.calculator import calculate_theoretical_target
from trafriend_api.domain.daily_close import DailyCloseAnchor, DailyCloseAnchorStatus
from trafriend_api.domain.errors import (
    AnchorUnavailableError,
    AnchorVersionInactiveError,
)
from trafriend_api.domain.models import (
    CalculationResult,
    Instrument,
    LeveragedRelationship,
    ProfitRatioHistory,
)


class MarketDataService:
    def __init__(
        self,
        provider: MarketDataProvider,
        anchor_service: DailyCloseAnchorService,
        relationship_catalog: LeveragedRelationshipCatalog,
    ) -> None:
        self._provider = provider
        self._anchor_service = anchor_service
        self._relationship_catalog = relationship_catalog

    @property
    def provider_code(self) -> str:
        return self._provider.provider_code

    def search_instruments(self, query: str, limit: int = 10) -> Sequence[Instrument]:
        return self._relationship_catalog.search_instruments(query=query, limit=limit)

    def get_instrument(self, instrument_id: str) -> Instrument:
        return self._relationship_catalog.get_instrument(instrument_id)

    def get_leveraged_relationships(
        self, instrument_id: str
    ) -> Sequence[LeveragedRelationship]:
        return self._relationship_catalog.get_leveraged_relationships(instrument_id)

    def get_relationship(self, relationship_id: str) -> LeveragedRelationship:
        return self._relationship_catalog.get_relationship(relationship_id)

    def get_anchor(self, relationship_id: str) -> DailyCloseAnchor:
        self._relationship_catalog.get_relationship(relationship_id)
        return self._anchor_service.latest(relationship_id)

    def calculate(
        self,
        relationship_id: str,
        anchor_version_id: str,
        input_side: str,
        target_price: Decimal,
    ) -> CalculationResult:
        relationship = self._relationship_catalog.get_relationship(relationship_id)
        anchor = self._anchor_service.latest(relationship_id)
        if anchor.id != anchor_version_id:
            raise AnchorVersionInactiveError(
                "the submitted Daily Close Anchor version is no longer active"
            )
        if anchor.status != DailyCloseAnchorStatus.COMPLETE:
            raise AnchorUnavailableError(
                "a complete same-date Daily Close Anchor is required"
            )
        return calculate_theoretical_target(
            relationship=relationship,
            anchor=anchor,
            input_side=input_side,
            target_price=target_price,
        )

    def get_profit_ratio_history(
        self, instrument_id: str, start: date, end: date
    ) -> ProfitRatioHistory:
        return self._provider.get_profit_ratio_history(instrument_id, start, end)
