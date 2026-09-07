from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True)
class SupportedLeveragedProduct:
    symbol: str
    signed_leverage: Decimal


@dataclass(frozen=True)
class SupportedAssetGroup:
    underlying_symbol: str
    leveraged_products: tuple[SupportedLeveragedProduct, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return (self.underlying_symbol,) + tuple(
            product.symbol for product in self.leveraged_products
        )


@dataclass(frozen=True)
class SupportedUniverse:
    """Static allow-list retained for the isolated overnight diagnostic CLI."""

    groups: tuple[SupportedAssetGroup, ...]

    def group_for(self, symbol: str) -> SupportedAssetGroup:
        normalized = symbol.strip().upper()
        for group in self.groups:
            if normalized in group.symbols:
                return group
        raise KeyError(f"unsupported overnight symbol: {normalized}")


DEFAULT_SUPPORTED_UNIVERSE = SupportedUniverse(
    groups=(
        SupportedAssetGroup(
            "SNDK", (SupportedLeveragedProduct("SNXX", Decimal("2")),)
        ),
        SupportedAssetGroup(
            "NVDA", (SupportedLeveragedProduct("NVDL", Decimal("2")),)
        ),
        SupportedAssetGroup(
            "TSLA", (SupportedLeveragedProduct("TSLL", Decimal("2")),)
        ),
        SupportedAssetGroup(
            "QQQ",
            (
                SupportedLeveragedProduct("QLD", Decimal("2")),
                SupportedLeveragedProduct("TQQQ", Decimal("3")),
                SupportedLeveragedProduct("SQQQ", Decimal("-3")),
            ),
        ),
        SupportedAssetGroup(
            "SOXX",
            (
                SupportedLeveragedProduct("SOXL", Decimal("3")),
                SupportedLeveragedProduct("SOXS", Decimal("-3")),
            ),
        ),
    )
)


class RankingType(str, Enum):
    DOLLAR_TRADING_VOLUME = "DOLLAR_TRADING_VOLUME"


class RankingPeriodStatus(str, Enum):
    SEPTEMBER_TO_DATE = "SEPTEMBER_TO_DATE"
    FINAL = "FINAL"


class RankingPopulationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_POPULATED = "NOT_POPULATED"


class RankingCompletenessStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class RankingAsset:
    symbol: str
    name: str
    exchange: str
    status: str
    tradable: bool


@dataclass(frozen=True)
class RankingDailyBar:
    symbol: str
    trading_date: date
    vwap: Decimal
    volume: Decimal
    source: str
    source_feed: str

    def __post_init__(self) -> None:
        if not self.vwap.is_finite() or self.vwap <= 0:
            raise ValueError("ranking daily VWAP must be finite and positive")
        if not self.volume.is_finite() or self.volume <= 0:
            raise ValueError("ranking daily volume must be finite and positive")


@dataclass(frozen=True)
class MarketRanking:
    ranking_period: str
    period_start: date
    period_end: date
    period_status: RankingPeriodStatus
    ranking_type: RankingType
    rank: int
    symbol: str
    trading_metric: Decimal
    calculated_at: datetime
    source: str
    display_name: str = ""
    exchange: str = ""
    completeness_status: RankingCompletenessStatus = (
        RankingCompletenessStatus.COMPLETE
    )
    sessions_observed: int = 0
    sessions_expected: int = 0

    def __post_init__(self) -> None:
        if not self.ranking_period.strip():
            raise ValueError("market ranking period cannot be empty")
        if self.rank < 1 or self.rank > 100:
            raise ValueError("market ranking rank must be between 1 and 100")
        if not self.symbol.strip() or len(self.symbol.strip()) > 16:
            raise ValueError("market ranking symbol must contain 1 to 16 characters")
        if not self.trading_metric.is_finite() or self.trading_metric < 0:
            raise ValueError("market ranking metric must be finite and non-negative")
        if self.period_start > self.period_end:
            raise ValueError("ranking period start cannot follow its end")
        if self.calculated_at.tzinfo is None or self.calculated_at.utcoffset() is None:
            raise ValueError("ranking calculated_at must be timezone-aware")
        if not self.source.strip():
            raise ValueError("market ranking source cannot be empty")
        if self.sessions_observed < 0 or self.sessions_expected < 0:
            raise ValueError("ranking session counts cannot be negative")
        if self.sessions_observed > self.sessions_expected:
            raise ValueError("observed ranking sessions cannot exceed expected sessions")
        if (
            self.completeness_status == RankingCompletenessStatus.COMPLETE
            and self.sessions_observed != self.sessions_expected
        ):
            raise ValueError("complete ranking rows must include every expected session")


@dataclass(frozen=True)
class RankingBuildReport:
    ranking_period: str
    completed_trading_dates: tuple[date, ...]
    candidate_assets: int
    complete_assets: int
    incomplete_assets: int
    persisted_rows: int
    rows: tuple[MarketRanking, ...]


@dataclass(frozen=True)
class PopularDataset:
    ranking_period: str
    period_status: RankingPeriodStatus
    ranking_type: RankingType
    population_status: RankingPopulationStatus
    rows: tuple[MarketRanking, ...]


@dataclass(frozen=True)
class RelationshipAnchorState:
    relationship_id: str
    status: str
    anchor_source: str
    message: str
    anchor_id: str | None = None
