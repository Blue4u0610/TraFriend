from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class DailyCloseQuality(str, Enum):
    REALTIME = "REALTIME"
    DELAYED = "DELAYED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class DailyCloseValueStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    REJECTED = "REJECTED"
    MISSING = "MISSING"


class DailyCloseAnchorStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


def _require_aware(timestamp: datetime, field_name: str) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_positive(value: Decimal, field_name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be finite and positive")


@dataclass(frozen=True)
class CompletedTradingSession:
    trading_date: date
    closed_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.closed_at, "closed_at")


@dataclass(frozen=True)
class DailyCloseBar:
    symbol: str
    trading_date: date
    close: Decimal
    market_timestamp: datetime
    observed_at: datetime
    source: str
    source_feed: str
    currency: str
    quality: DailyCloseQuality

    def __post_init__(self) -> None:
        _require_positive(self.close, "close")
        _require_aware(self.market_timestamp, "market_timestamp")
        _require_aware(self.observed_at, "observed_at")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise ValueError("currency must be a three-letter uppercase code")


@dataclass(frozen=True)
class DailyCloseAnchorValue:
    symbol: str
    close: Optional[Decimal]
    trading_date: Optional[date]
    market_timestamp: Optional[datetime]
    observed_at: datetime
    source: str
    source_feed: str
    currency: str
    quality: DailyCloseQuality
    status: DailyCloseValueStatus
    message: str

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise ValueError("currency must be a three-letter uppercase code")
        if self.market_timestamp is not None:
            _require_aware(self.market_timestamp, "market_timestamp")
        if self.close is not None:
            _require_positive(self.close, "close")
        if self.status == DailyCloseValueStatus.AVAILABLE:
            if (
                self.close is None
                or self.trading_date is None
                or self.market_timestamp is None
            ):
                raise ValueError("an available daily close must be complete")
            if self.quality in {
                DailyCloseQuality.STALE,
                DailyCloseQuality.UNAVAILABLE,
            }:
                raise ValueError("an available daily close must have usable quality")
        if self.status == DailyCloseValueStatus.MISSING:
            if any(
                value is not None
                for value in (self.close, self.trading_date, self.market_timestamp)
            ):
                raise ValueError("a missing daily close cannot contain market data")
            if self.quality != DailyCloseQuality.UNAVAILABLE:
                raise ValueError("a missing daily close must be UNAVAILABLE")


@dataclass(frozen=True)
class DailyCloseAnchor:
    id: str
    relationship_id: str
    trading_date: date
    status: DailyCloseAnchorStatus
    version: int
    underlying: DailyCloseAnchorValue
    leveraged_product: DailyCloseAnchorValue
    session_closed_at: datetime
    captured_at: datetime
    provider: str
    source_feed: str
    signed_leverage: Decimal
    created_at: datetime
    anchor_type: str = "DAILY_CLOSE_ANCHOR"

    def __post_init__(self) -> None:
        _require_aware(self.session_closed_at, "session_closed_at")
        _require_aware(self.captured_at, "captured_at")
        _require_aware(self.created_at, "created_at")
        if not self.signed_leverage.is_finite() or self.signed_leverage == 0:
            raise ValueError("signed_leverage must be finite and non-zero")
        if self.version < 0:
            raise ValueError("version cannot be negative")
        if self.session_closed_at > self.captured_at:
            raise ValueError("an anchor cannot precede the completed session close")
        if self.underlying.symbol == self.leveraged_product.symbol:
            raise ValueError("anchor members must be different instruments")
        available = (
            self.underlying.status == DailyCloseValueStatus.AVAILABLE,
            self.leveraged_product.status == DailyCloseValueStatus.AVAILABLE,
        )
        expected_status = (
            DailyCloseAnchorStatus.COMPLETE
            if all(available)
            else DailyCloseAnchorStatus.PARTIAL
            if any(available)
            else DailyCloseAnchorStatus.UNAVAILABLE
        )
        if self.status != expected_status:
            raise ValueError("anchor status does not match its member values")
        if self.status == DailyCloseAnchorStatus.COMPLETE:
            if {
                self.underlying.trading_date,
                self.leveraged_product.trading_date,
            } != {self.trading_date}:
                raise ValueError("complete anchors cannot mix trading dates")
            provenance = {
                (self.underlying.source, self.underlying.source_feed),
                (
                    self.leveraged_product.source,
                    self.leveraged_product.source_feed,
                ),
            }
            if provenance != {(self.provider, self.source_feed)}:
                raise ValueError("complete anchors cannot mix provider provenance")
            if {self.underlying.currency, self.leveraged_product.currency} != {"USD"}:
                raise ValueError("complete U.S. anchors must use USD")


def daily_close_anchor_identity(anchor: DailyCloseAnchor) -> tuple[str, str, date]:
    """Return the immutable logical identity required for idempotent capture."""

    return (
        anchor.underlying.symbol,
        anchor.leveraged_product.symbol,
        anchor.trading_date,
    )


def daily_close_anchors_materially_equal(
    left: DailyCloseAnchor, right: DailyCloseAnchor
) -> bool:
    """Compare provider facts while ignoring retry observation/audit timestamps."""

    def value_facts(value: DailyCloseAnchorValue) -> tuple[object, ...]:
        return (
            value.symbol,
            value.close,
            value.trading_date,
            value.market_timestamp,
            value.source,
            value.source_feed,
            value.currency,
            value.quality,
            value.status,
        )

    return (
        left.relationship_id,
        left.trading_date,
        left.status,
        left.session_closed_at,
        left.provider,
        left.source_feed,
        left.signed_leverage,
        left.anchor_type,
        value_facts(left.underlying),
        value_facts(left.leveraged_product),
    ) == (
        right.relationship_id,
        right.trading_date,
        right.status,
        right.session_closed_at,
        right.provider,
        right.source_feed,
        right.signed_leverage,
        right.anchor_type,
        value_facts(right.underlying),
        value_facts(right.leveraged_product),
    )
