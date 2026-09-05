from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple


class ReferenceType(str, Enum):
    OVERNIGHT_OPEN = "OVERNIGHT_OPEN"
    OVERNIGHT_SNAPSHOT = "OVERNIGHT_SNAPSHOT"


class DataQuality(str, Enum):
    REALTIME = "REALTIME"
    DELAYED = "DELAYED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class ReferenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    REJECTED = "REJECTED"
    MISSING = "MISSING"


class CaptureStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class PriceBasis(str, Enum):
    BAR_OPEN = "BAR_OPEN"
    QUOTE_MIDPOINT = "QUOTE_MIDPOINT"


def _require_aware(timestamp: datetime, field_name: str) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_positive(value: Decimal, field_name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be finite and positive")


@dataclass(frozen=True)
class ProviderCapabilities:
    true_overnight: bool
    minute_bars: bool
    quotes: bool
    snapshots: bool
    batch_quotes: bool
    batch_bars: bool
    historical_overnight: bool


@dataclass(frozen=True)
class OvernightBar:
    symbol: str
    open_price: Decimal
    starts_at: datetime
    observed_at: datetime
    source: str
    source_feed: str
    quality: DataQuality

    def __post_init__(self) -> None:
        _require_positive(self.open_price, "open_price")
        _require_aware(self.starts_at, "starts_at")
        _require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True)
class HistoricalOvernightBar:
    """Normalized OHLCV bar retained only for manual provider diagnostics."""

    symbol: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    starts_at: datetime
    observed_at: datetime
    source: str
    source_feed: str
    quality: DataQuality

    def __post_init__(self) -> None:
        _require_positive(self.open_price, "open_price")
        _require_positive(self.high_price, "high_price")
        _require_positive(self.low_price, "low_price")
        _require_positive(self.close_price, "close_price")
        if self.high_price < max(self.open_price, self.close_price):
            raise ValueError("high_price cannot be below open_price or close_price")
        if self.low_price > min(self.open_price, self.close_price):
            raise ValueError("low_price cannot be above open_price or close_price")
        if not self.volume.is_finite() or self.volume < 0:
            raise ValueError("volume must be finite and non-negative")
        _require_aware(self.starts_at, "starts_at")
        _require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True)
class OvernightQuote:
    symbol: str
    price: Decimal
    market_timestamp: datetime
    observed_at: datetime
    source: str
    source_feed: str
    quality: DataQuality
    price_basis: PriceBasis = PriceBasis.QUOTE_MIDPOINT

    def __post_init__(self) -> None:
        _require_positive(self.price, "price")
        _require_aware(self.market_timestamp, "market_timestamp")
        _require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True)
class HistoricalOvernightQuote:
    """Normalized two-sided quote retained only for manual provider diagnostics."""

    symbol: str
    bid_price: Decimal
    ask_price: Decimal
    market_timestamp: datetime
    observed_at: datetime
    source: str
    source_feed: str
    quality: DataQuality

    def __post_init__(self) -> None:
        _require_positive(self.bid_price, "bid_price")
        _require_positive(self.ask_price, "ask_price")
        _require_aware(self.market_timestamp, "market_timestamp")
        _require_aware(self.observed_at, "observed_at")

    @property
    def midpoint(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")


@dataclass(frozen=True)
class OvernightReferenceValue:
    symbol: str
    trading_date: date
    price: Optional[Decimal]
    reference_type: ReferenceType
    source: str
    source_feed: str
    observed_at: datetime
    market_timestamp: Optional[datetime]
    quality: DataQuality
    status: ReferenceStatus
    price_basis: PriceBasis
    message: Optional[str] = None

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        if self.market_timestamp is not None:
            _require_aware(self.market_timestamp, "market_timestamp")
        if self.price is not None:
            _require_positive(self.price, "price")
        if self.status == ReferenceStatus.AVAILABLE and self.price is None:
            raise ValueError("an available reference must have a price")
        if self.status == ReferenceStatus.MISSING and self.quality != DataQuality.UNAVAILABLE:
            raise ValueError("a missing reference must be UNAVAILABLE")


@dataclass(frozen=True)
class OvernightReferenceCapture:
    id: str
    version: int
    trading_date: date
    reference_type: ReferenceType
    status: CaptureStatus
    values: Tuple[OvernightReferenceValue, ...]
    captured_at: datetime
    source: str
    source_feed: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        if self.version < 0:
            raise ValueError("version cannot be negative")
        if not self.values:
            raise ValueError("a capture must contain at least one requested symbol")
        if any(value.trading_date != self.trading_date for value in self.values):
            raise ValueError("capture values cannot mix trading dates")
        if any(value.reference_type != self.reference_type for value in self.values):
            raise ValueError("capture values cannot mix reference types")

    @property
    def synchronization_difference(self) -> Optional[timedelta]:
        timestamps = tuple(
            value.market_timestamp
            for value in self.values
            if value.market_timestamp is not None
        )
        if len(timestamps) < 2:
            return None
        return max(timestamps) - min(timestamps)
