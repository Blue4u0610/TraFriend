from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from trafriend_api.application.ports.daily_close import AnchorPersistenceOutcome
from trafriend_api.application.ports.market_data import LeveragedRelationshipCatalog
from trafriend_api.application.ports.ranking import MarketRankingRepository
from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.domain.calculator import calculate_theoretical_target
from trafriend_api.domain.daily_close import DailyCloseAnchor, DailyCloseAnchorStatus
from trafriend_api.domain.errors import (
    AnchorConflictError,
    AnchorUnavailableError,
    ResourceNotFoundError,
)
from trafriend_api.domain.models import (
    CalculationResult,
    Instrument,
    LeveragedRelationship,
)
from trafriend_api.domain.universe import PopularDataset, RankingType


@dataclass(frozen=True)
class AnchorResolution:
    relationship: LeveragedRelationship
    status: str
    anchor_source: str
    message: str
    anchor: DailyCloseAnchor | None


@dataclass(frozen=True)
class UnderlyingWorkspace:
    underlying: Instrument
    rows: tuple[AnchorResolution, ...]


@dataclass(frozen=True)
class MultiCalculationRow:
    relationship: LeveragedRelationship
    status: str
    anchor: DailyCloseAnchor | None
    result: CalculationResult | None
    message: str


@dataclass(frozen=True)
class MultiCalculation:
    underlying: Instrument
    target_price: Decimal
    rows: tuple[MultiCalculationRow, ...]


@dataclass(frozen=True)
class CaptureItem:
    relationship_id: str
    underlying_symbol: str
    leveraged_product_symbol: str
    status: str
    message: str
    anchor: DailyCloseAnchor | None


@dataclass(frozen=True)
class DailyCaptureReport:
    trading_date: str
    status: str
    underlying_symbols: tuple[str, ...]
    leveraged_product_symbols: tuple[str, ...]
    items: tuple[CaptureItem, ...]

    @property
    def inserted(self) -> int:
        return sum(item.status == "INSERTED" for item in self.items)

    @property
    def existing(self) -> int:
        return sum(item.status == "EXISTING" for item in self.items)

    @property
    def skipped_no_supported_product(self) -> int:
        return sum(
            item.status == "SKIPPED_NO_SUPPORTED_PRODUCT" for item in self.items
        )

    @property
    def unavailable(self) -> int:
        return sum(item.status == "UNAVAILABLE" for item in self.items)

    @property
    def conflicts(self) -> int:
        return sum(item.status == "CONFLICT" for item in self.items)


class UniverseService:
    """Curated metadata, cache resolution, and multi-product calculation use cases."""

    def __init__(
        self,
        catalog: LeveragedRelationshipCatalog,
        ranking_repository: MarketRankingRepository,
        anchor_service: DailyCloseAnchorService,
        capture_enabled: bool = True,
    ) -> None:
        self._catalog = catalog
        self._ranking_repository = ranking_repository
        self._anchor_service = anchor_service
        self._capture_enabled = capture_enabled

    def search(self, query: str, limit: int = 10) -> Sequence[Instrument]:
        return self._catalog.search_instruments(query, limit)

    def search_underlyings(
        self, query: str, limit: int = 10
    ) -> Sequence[Instrument]:
        return self._catalog.search_underlyings(query, limit)

    def search_leveraged_products(
        self, query: str, limit: int = 10
    ) -> Sequence[Instrument]:
        return self._catalog.search_leveraged_products(query, limit)

    def get_underlying(self, symbol: str) -> Instrument:
        selected = self._catalog.get_instrument_by_symbol(symbol)
        relationships = self._catalog.get_leveraged_relationships(selected.id)
        return relationships[0].underlying if relationships else selected

    def relationships(self, symbol: str) -> Sequence[LeveragedRelationship]:
        selected = self._catalog.get_instrument_by_symbol(symbol)
        return self._catalog.get_leveraged_relationships(selected.id)

    def popular(
        self,
        ranking_period: str = "2026-09",
        ranking_type: RankingType = RankingType.DOLLAR_TRADING_VOLUME,
        limit: int = 100,
    ) -> PopularDataset:
        return self._ranking_repository.get_dataset(
            ranking_period, ranking_type, limit
        )

    def resolve(self, symbol: str, capture_missing: bool) -> UnderlyingWorkspace:
        underlying = self.get_underlying(symbol)
        relationships = self._catalog.get_leveraged_relationships(underlying.id)
        rows = tuple(
            self._resolve_relationship(relationship, capture_missing)
            for relationship in relationships
        )
        return UnderlyingWorkspace(underlying=underlying, rows=rows)

    def calculate_all(
        self, symbol: str, target_price: Decimal
    ) -> MultiCalculation:
        underlying = self.get_underlying(symbol)
        rows: list[MultiCalculationRow] = []
        for relationship in self._catalog.get_leveraged_relationships(underlying.id):
            try:
                anchor = self._anchor_service.latest(relationship.id)
            except AnchorUnavailableError:
                rows.append(
                    MultiCalculationRow(
                        relationship=relationship,
                        status="UNAVAILABLE",
                        anchor=None,
                        result=None,
                        message=(
                            "No complete same-date anchor exists for the latest "
                            "completed regular session"
                        ),
                    )
                )
                continue
            result = calculate_theoretical_target(
                relationship=relationship,
                anchor=anchor,
                input_side="underlying",
                target_price=target_price,
            )
            rows.append(
                MultiCalculationRow(
                    relationship=relationship,
                    status="AVAILABLE",
                    anchor=anchor,
                    result=result,
                    message="calculated from persisted Daily Close Anchor",
                )
            )
        return MultiCalculation(
            underlying=underlying,
            target_price=target_price,
            rows=tuple(rows),
        )

    def capture_popular(
        self,
        ranking_period: str = "2026-09",
    ) -> DailyCaptureReport:
        dataset = self.popular(ranking_period=ranking_period)
        return self._capture_symbols(
            tuple(row.symbol for row in dataset.rows),
            skip_no_supported_product=True,
        )

    def capture_symbols(self, symbols: Sequence[str]) -> DailyCaptureReport:
        return self._capture_symbols(symbols, skip_no_supported_product=False)

    def _capture_symbols(
        self,
        symbols: Sequence[str],
        skip_no_supported_product: bool,
    ) -> DailyCaptureReport:
        session = self._anchor_service.expected_session()
        underlying_symbols: set[str] = set()
        leveraged_symbols: set[str] = set()
        items: list[CaptureItem] = []
        for symbol in dict.fromkeys(item.strip().upper() for item in symbols if item.strip()):
            try:
                underlying = self.get_underlying(symbol)
                relationships = self._catalog.get_leveraged_relationships(underlying.id)
            except ResourceNotFoundError as exc:
                if skip_no_supported_product:
                    underlying_symbols.add(symbol)
                    items.append(
                        self._skipped_no_supported_product(symbol)
                    )
                    continue
                items.append(
                    CaptureItem(
                        relationship_id="",
                        underlying_symbol=symbol,
                        leveraged_product_symbol="",
                        status="UNAVAILABLE",
                        message=f"unsupported universe symbol: {exc.__class__.__name__}",
                        anchor=None,
                    )
                )
                continue
            underlying_symbols.add(underlying.symbol)
            if not relationships:
                items.append(
                    self._skipped_no_supported_product(underlying.symbol)
                    if skip_no_supported_product
                    else CaptureItem(
                        relationship_id="",
                        underlying_symbol=underlying.symbol,
                        leveraged_product_symbol="",
                        status="UNAVAILABLE",
                        message="underlying has no supported leveraged products",
                        anchor=None,
                    )
                )
                continue
            for relationship in relationships:
                leveraged_symbols.add(relationship.leveraged_product.symbol)
                if not self._capture_enabled:
                    items.append(
                        CaptureItem(
                            relationship_id=relationship.id,
                            underlying_symbol=relationship.underlying.symbol,
                            leveraged_product_symbol=(
                                relationship.leveraged_product.symbol
                            ),
                            status="UNAVAILABLE",
                            message=(
                                "real daily-close capture is not enabled for this "
                                "PostgreSQL application"
                            ),
                            anchor=None,
                        )
                    )
                    continue
                try:
                    result = self._anchor_service.capture_with_result(
                        relationship.id,
                        relationship.underlying.symbol,
                        relationship.leveraged_product.symbol,
                        relationship.leverage_factor,
                    )
                    status = (
                        result.outcome.value
                        if result.outcome != AnchorPersistenceOutcome.NOT_PERSISTED
                        else "UNAVAILABLE"
                    )
                    message = (
                        "complete anchor persisted"
                        if result.anchor.status == DailyCloseAnchorStatus.COMPLETE
                        else result.anchor.leveraged_product.message
                    )
                    items.append(
                        CaptureItem(
                            relationship_id=relationship.id,
                            underlying_symbol=relationship.underlying.symbol,
                            leveraged_product_symbol=(
                                relationship.leveraged_product.symbol
                            ),
                            status=status,
                            message=message,
                            anchor=result.anchor,
                        )
                    )
                except AnchorConflictError as exc:
                    items.append(
                        CaptureItem(
                            relationship_id=relationship.id,
                            underlying_symbol=relationship.underlying.symbol,
                            leveraged_product_symbol=(
                                relationship.leveraged_product.symbol
                            ),
                            status="CONFLICT",
                            message=f"capture failed: {exc.__class__.__name__}",
                            anchor=None,
                        )
                    )
        completed = sum(
            item.status
            in {"INSERTED", "EXISTING", "SKIPPED_NO_SUPPORTED_PRODUCT"}
            for item in items
        )
        failed = len(items) - completed
        status = (
            "COMPLETE"
            if items and failed == 0
            else "PARTIAL"
            if completed
            else "FAILED"
        )
        return DailyCaptureReport(
            trading_date=session.trading_date.isoformat(),
            status=status,
            underlying_symbols=tuple(sorted(underlying_symbols)),
            leveraged_product_symbols=tuple(sorted(leveraged_symbols)),
            items=tuple(items),
        )

    @staticmethod
    def _skipped_no_supported_product(symbol: str) -> CaptureItem:
        return CaptureItem(
            relationship_id="",
            underlying_symbol=symbol,
            leveraged_product_symbol="",
            status="SKIPPED_NO_SUPPORTED_PRODUCT",
            message="ranked underlying has no active supported leveraged product",
            anchor=None,
        )

    def _resolve_relationship(
        self,
        relationship: LeveragedRelationship,
        capture_missing: bool,
    ) -> AnchorResolution:
        try:
            anchor = self._anchor_service.latest(relationship.id)
            return AnchorResolution(
                relationship=relationship,
                status="AVAILABLE",
                anchor_source="CACHE",
                message="current anchor loaded from PostgreSQL",
                anchor=anchor,
            )
        except AnchorUnavailableError:
            if not capture_missing:
                return AnchorResolution(
                    relationship=relationship,
                    status="UNAVAILABLE",
                    anchor_source="NONE",
                    message="current anchor is not cached",
                    anchor=None,
                )
            if not self._capture_enabled:
                return AnchorResolution(
                    relationship=relationship,
                    status="UNAVAILABLE",
                    anchor_source="NONE",
                    message=(
                        "real on-demand capture is disabled; configure the Alpaca "
                        "daily-close provider"
                    ),
                    anchor=None,
                )
        result = self._anchor_service.capture_with_result(
            relationship.id,
            relationship.underlying.symbol,
            relationship.leveraged_product.symbol,
            relationship.leverage_factor,
        )
        if result.anchor.status != DailyCloseAnchorStatus.COMPLETE:
            return AnchorResolution(
                relationship=relationship,
                status="UNAVAILABLE",
                anchor_source="ON_DEMAND",
                message=result.anchor.leveraged_product.message,
                anchor=result.anchor,
            )
        return AnchorResolution(
            relationship=relationship,
            status="AVAILABLE",
            anchor_source="ON_DEMAND",
            message="latest completed-session anchor captured and cached",
            anchor=result.anchor,
        )
