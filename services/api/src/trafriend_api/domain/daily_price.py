"""Independent completed-session stock-price bars, never calculator anchors."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Optional

from trafriend_api.domain.errors import TraFriendDomainError


class DailyPriceConflictError(TraFriendDomainError):
    """A same-date immutable price bar conflicts with stored source facts."""


@dataclass(frozen=True)
class DailyPriceBar:
    id: str
    instrument_id: str
    symbol: str
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    previous_close: Optional[Decimal]
    session_opened_at: datetime
    session_closed_at: datetime
    market_timestamp: datetime
    observed_at: datetime
    provider: str
    source_feed: str
    quality: str
    currency: str = "USD"
    adjustment: str = "raw"
    price_scope: str = "CONSOLIDATED_DAILY_ELIGIBLE_TRADES"

    def __post_init__(self) -> None:
        prices: tuple[Decimal, ...] = (self.open, self.high, self.low, self.close)
        if self.previous_close is not None:
            prices += (self.previous_close,)
        if any(
            not value.is_finite() or not Decimal(0) < value < Decimal("1e16") for value in prices
        ):
            raise ValueError("daily prices must be finite, positive, and in supported bounds")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("daily OHLC ordering is invalid")
        for instant in (
            self.session_opened_at,
            self.session_closed_at,
            self.market_timestamp,
            self.observed_at,
        ):
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise ValueError("daily price timestamps must be timezone-aware")
        if (
            not self.market_timestamp
            <= self.session_opened_at
            < self.session_closed_at
            <= self.observed_at
        ):
            raise ValueError("daily bars require a completed session and ordered timestamps")
        if self.currency != "USD" or self.adjustment != "raw":
            raise ValueError("daily candles use USD raw prices and explicit split-basis returns")
        if self.price_scope != "CONSOLIDATED_DAILY_ELIGIBLE_TRADES":
            raise ValueError("daily price scope must be explicitly supported")
        if not all((self.instrument_id, self.symbol, self.provider, self.source_feed)):
            raise ValueError("daily bars require instrument and provider provenance")
        if self.quality not in {"REALTIME", "DELAYED", "MOCK"}:
            raise ValueError("only available quality can be persisted as a complete daily bar")

    @property
    def price_change_return(self) -> Optional[Decimal]:
        if self.previous_close is None:
            return None
        with localcontext() as context:
            context.prec = 40
            return self.close / self.previous_close - 1


def daily_price_bars_equal(left: DailyPriceBar, right: DailyPriceBar) -> bool:
    """Retry observation time and generated identity are not market corrections."""
    return replace(left, id=right.id, observed_at=right.observed_at) == right
