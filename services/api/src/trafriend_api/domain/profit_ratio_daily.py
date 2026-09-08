"""Daily endpoint observations, not fabricated Profit Ratio OHLC bars."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, localcontext
from enum import Enum
from typing import Optional, Tuple

from trafriend_api.domain.errors import TraFriendDomainError


class ProfitRatioConflictError(TraFriendDomainError):
    """A retry conflicts with an immutable observation or price."""


class ProfitRatioCalendarRangeError(TraFriendDomainError, ValueError):
    """Requested dates are outside the available exchange-calendar coverage."""


class ProfitRatioPhase(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"


class ProfitRatioStatus(str, Enum):
    ESTIMATED = "ESTIMATED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("market and observation timestamps must be timezone-aware")


def _positive(value: Decimal) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError("financial values must be finite and positive")


def _ratio(value: Decimal) -> None:
    if not value.is_finite() or not Decimal(0) <= value <= Decimal(1):
        raise ValueError("ratios must be finite and in [0, 1]")


@dataclass(frozen=True)
class NasdaqConstituent:
    instrument_id: str
    symbol: str
    name: str
    as_of: date
    source: str

    def __post_init__(self) -> None:
        if not all((self.instrument_id, self.symbol, self.name, self.source)):
            raise ValueError("constituent identity and sourced metadata are required")
        if self.symbol != self.symbol.strip().upper() or len(self.symbol) > 20:
            raise ValueError("constituent symbols must be canonical uppercase text")


@dataclass(frozen=True)
class ProfitRatioSession:
    trading_date: date
    opened_at: datetime
    closed_at: datetime
    previous_trading_date: date

    def __post_init__(self) -> None:
        _aware(self.opened_at)
        _aware(self.closed_at)
        if self.opened_at >= self.closed_at or self.previous_trading_date >= self.trading_date:
            raise ValueError("session ordering is invalid")

    def instant(self, phase: ProfitRatioPhase) -> datetime:
        return self.opened_at if phase == ProfitRatioPhase.OPEN else self.closed_at


@dataclass(frozen=True)
class ProfitRatioObservation:
    id: str
    instrument_id: str
    symbol: str
    trading_date: date
    phase: ProfitRatioPhase
    ratio: Optional[Decimal]
    market_timestamp: datetime
    observed_at: datetime
    provider: str
    source_feed: str
    quality: str
    status: ProfitRatioStatus
    reason_code: str
    methodology_key: str = "CHIP_TURNOVER"
    methodology_version: str = "1"
    version: int = 1

    def __post_init__(self) -> None:
        _aware(self.market_timestamp)
        _aware(self.observed_at)
        if self.observed_at < self.market_timestamp:
            raise ValueError("observation cannot precede its market-effective instant")
        if self.version < 1:
            raise ValueError("observation versions must be positive")
        if not all(
            (self.provider, self.source_feed, self.methodology_key, self.methodology_version)
        ):
            raise ValueError("observations require provider and methodology provenance")
        if self.ratio is not None:
            _ratio(self.ratio)
        if (self.status == ProfitRatioStatus.ESTIMATED) != (self.ratio is not None):
            raise ValueError("insufficient observations cannot contain a fabricated ratio")
        if self.status == ProfitRatioStatus.DATA_INSUFFICIENT and not self.reason_code:
            raise ValueError("insufficient observations require an explicit reason")


@dataclass(frozen=True)
class ProfitRatioPriceObservation:
    """Separate regular-session price context; no leveraged anchor dependency."""

    instrument_id: str
    symbol: str
    trading_date: date
    phase: ProfitRatioPhase
    price: Decimal
    previous_close: Optional[Decimal]
    market_timestamp: datetime
    observed_at: datetime
    provider: str
    source_feed: str
    currency: str = "USD"

    def __post_init__(self) -> None:
        _positive(self.price)
        if self.previous_close is not None:
            _positive(self.previous_close)
        _aware(self.market_timestamp)
        _aware(self.observed_at)
        if self.observed_at < self.market_timestamp:
            raise ValueError("price observation cannot precede its market instant")
        if self.currency != "USD" or not self.provider or not self.source_feed:
            raise ValueError("price provenance and USD currency are required")


@dataclass(frozen=True)
class ProfitRatioRecord:
    observation: ProfitRatioObservation
    price: ProfitRatioPriceObservation

    def __post_init__(self) -> None:
        observation = self.observation
        price = self.price
        if (
            observation.instrument_id,
            observation.symbol,
            observation.trading_date,
            observation.phase,
            observation.market_timestamp,
            observation.provider,
            observation.source_feed,
        ) != (
            price.instrument_id,
            price.symbol,
            price.trading_date,
            price.phase,
            price.market_timestamp,
            price.provider,
            price.source_feed,
        ):
            raise ValueError("ratio and price context cannot mix identities or provenance")


def price_observations_equal(
    left: ProfitRatioPriceObservation, right: ProfitRatioPriceObservation
) -> bool:
    return replace(left, observed_at=right.observed_at) == right


def profit_ratio_records_equal(left: ProfitRatioRecord, right: ProfitRatioRecord) -> bool:
    return (
        price_observations_equal(left.price, right.price)
        and replace(
            left.observation,
            id=right.observation.id,
            observed_at=right.observation.observed_at,
            version=right.observation.version,
        )
        == right.observation
    )


@dataclass(frozen=True)
class FloatSnapshot:
    instrument_id: str
    shares: Decimal
    effective_from: date
    effective_to: date
    source: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _positive(self.shares)
        _aware(self.observed_at)
        if not self.source or self.effective_to < self.effective_from:
            raise ValueError("float requires sourced, effective-dated coverage")


@dataclass(frozen=True)
class CostBin:
    cost: Decimal
    weight: Decimal

    def __post_init__(self) -> None:
        _positive(self.cost)
        _ratio(self.weight)


@dataclass(frozen=True)
class ChipDistribution:
    instrument_id: str
    trading_date: date
    bins: Tuple[CostBin, ...]
    source: str
    seed_validated: bool
    methodology_key: str = "CHIP_TURNOVER"
    methodology_version: str = "1"

    def __post_init__(self) -> None:
        with localcontext() as context:
            context.prec = 50
            total = sum((item.weight for item in self.bins), Decimal(0))
        if not self.bins or total != Decimal(1) or not self.source:
            raise ValueError("a sourced cost distribution must have total weight one")
        if len({item.cost for item in self.bins}) != len(self.bins):
            raise ValueError("cost bins must have distinct price identities")


@dataclass(frozen=True)
class ProfitRatioMinute:
    market_timestamp: datetime
    vwap: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        _aware(self.market_timestamp)
        _positive(self.vwap)
        if not self.volume.is_finite() or self.volume < 0:
            raise ValueError("minute volume must be finite and non-negative")


@dataclass(frozen=True)
class ProfitRatioCaptureInput:
    price: ProfitRatioPriceObservation
    quality: str = "DELAYED"
    float_snapshot: Optional[FloatSnapshot] = None
    prior_distribution: Optional[ChipDistribution] = None
    minutes: Tuple[ProfitRatioMinute, ...] = ()
    corporate_actions_verified: bool = False
    minute_coverage_complete: bool = False


@dataclass(frozen=True)
class ProfitRatioModelResult:
    ratio: Optional[Decimal]
    reason_code: str
    distribution: Optional[ChipDistribution] = None


def calculate_endpoint(
    inputs: ProfitRatioCaptureInput, session: ProfitRatioSession
) -> ProfitRatioModelResult:
    """Candidate model only: never invent a float, seed, or corporate-action basis."""

    price = inputs.price
    prior = inputs.prior_distribution
    snapshot = inputs.float_snapshot
    if price.trading_date != session.trading_date:
        return ProfitRatioModelResult(None, "SESSION_MISMATCH")
    if prior is None or not prior.seed_validated:
        return ProfitRatioModelResult(None, "VALIDATED_PRIOR_DISTRIBUTION_MISSING")
    if (
        prior.instrument_id != price.instrument_id
        or prior.trading_date != session.previous_trading_date
        or prior.methodology_key != "CHIP_TURNOVER"
        or prior.methodology_version != "1"
    ):
        return ProfitRatioModelResult(None, "PRIOR_DISTRIBUTION_MISMATCH")
    if snapshot is None:
        return ProfitRatioModelResult(None, "EFFECTIVE_DATED_FLOAT_MISSING")
    if (
        snapshot.instrument_id != price.instrument_id
        or not snapshot.effective_from <= session.trading_date <= snapshot.effective_to
        or snapshot.observed_at > price.observed_at
    ):
        return ProfitRatioModelResult(None, "FLOAT_DATE_MISMATCH")
    if not inputs.corporate_actions_verified:
        return ProfitRatioModelResult(None, "CORPORATE_ACTION_BASIS_UNVERIFIED")
    distribution = prior
    if price.phase == ProfitRatioPhase.CLOSE:
        if not inputs.minute_coverage_complete or not inputs.minutes:
            return ProfitRatioModelResult(None, "REGULAR_SESSION_MINUTES_INCOMPLETE")
        timestamps = tuple(item.market_timestamp for item in inputs.minutes)
        if timestamps != tuple(sorted(set(timestamps))) or any(
            not session.opened_at <= instant < session.closed_at for instant in timestamps
        ):
            return ProfitRatioModelResult(None, "MINUTE_SESSION_OR_ORDER_INVALID")
        with localcontext() as context:
            context.prec = 50
            weights = {item.cost: item.weight for item in prior.bins}
            for minute in inputs.minutes:
                retained = (-minute.volume / snapshot.shares).exp()
                weights = {cost: weight * retained for cost, weight in weights.items()}
                weights[minute.vwap] = weights.get(minute.vwap, Decimal(0)) + (1 - retained)
                # Decimal exponent rounding must not accumulate probability mass error.
                largest = max(weights, key=lambda cost: weights[cost])
                weights[largest] += Decimal(1) - sum(weights.values(), Decimal(0))
            distribution = ChipDistribution(
                instrument_id=prior.instrument_id,
                trading_date=session.trading_date,
                bins=tuple(CostBin(cost, weight) for cost, weight in sorted(weights.items())),
                source=prior.source,
                seed_validated=True,
            )
    with localcontext() as context:
        context.prec = 50
        ratio = sum(
            (item.weight for item in distribution.bins if item.cost < price.price), Decimal(0)
        )
    return ProfitRatioModelResult(ratio, "", distribution)
