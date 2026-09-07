from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Dict, Sequence

from trafriend_api.application.ports.daily_close import (
    AnchorPersistenceOutcome,
    CompletedSessionCalendar,
    DailyCloseAnchorPersistenceResult,
    DailyCloseAnchorRepository,
    DailyCloseMarketDataProvider,
)
from trafriend_api.domain.daily_close import (
    CompletedTradingSession,
    DailyCloseAnchor,
    DailyCloseAnchorStatus,
    DailyCloseAnchorValue,
    DailyCloseBar,
    DailyCloseQuality,
    DailyCloseValueStatus,
)
from trafriend_api.domain.errors import AnchorUnavailableError, MarketDataProviderError

UTC = timezone.utc


class DailyCloseAnchorService:
    """Captures one same-date regular-session close pair for calculator reads."""

    def __init__(
        self,
        provider: DailyCloseMarketDataProvider,
        calendar: CompletedSessionCalendar,
        repository: DailyCloseAnchorRepository,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._provider = provider
        self._calendar = calendar
        self._repository = repository
        self._now = now

    def capture(
        self,
        relationship_id: str,
        underlying_symbol: str,
        leveraged_product_symbol: str,
        signed_leverage: Decimal,
    ) -> DailyCloseAnchor:
        return self.capture_with_result(
            relationship_id,
            underlying_symbol,
            leveraged_product_symbol,
            signed_leverage,
        ).anchor

    def capture_with_result(
        self,
        relationship_id: str,
        underlying_symbol: str,
        leveraged_product_symbol: str,
        signed_leverage: Decimal,
    ) -> DailyCloseAnchorPersistenceResult:
        requested_at = self._utc_now()
        session = self._calendar.latest_completed_session(requested_at)
        symbols = self._normalize_pair(
            underlying_symbol, leveraged_product_symbol
        )
        try:
            bars = self._provider.get_daily_close_bars(
                symbols, session.trading_date, session.trading_date
            )
        except MarketDataProviderError as exc:
            captured_at = self._utc_now()
            values = tuple(
                self._missing_value(
                    symbol,
                    captured_at,
                    f"provider failure: {exc.__class__.__name__}",
                )
                for symbol in symbols
            )
            return self._store(
                relationship_id,
                session,
                values[0],
                values[1],
                signed_leverage,
                captured_at,
            )

        by_symbol: Dict[str, list[DailyCloseBar]] = {
            symbol: [] for symbol in symbols
        }
        for bar in bars:
            symbol = bar.symbol.strip().upper()
            if symbol in by_symbol:
                by_symbol[symbol].append(bar)

        captured_at = self._utc_now()
        values = tuple(
            self._value_for(symbol, by_symbol[symbol], session, captured_at)
            for symbol in symbols
        )
        return self._store(
            relationship_id,
            session,
            values[0],
            values[1],
            signed_leverage,
            captured_at,
        )

    def latest(self, relationship_id: str) -> DailyCloseAnchor:
        anchor = self._repository.latest(relationship_id)
        expected = self._calendar.latest_completed_session(
            self._utc_now()
        ).trading_date
        if anchor.trading_date != expected:
            raise AnchorUnavailableError(
                "Daily Close Anchor is unavailable for the latest completed session"
            )
        return anchor

    def expected_session(self) -> CompletedTradingSession:
        """Return the calendar-derived latest completed regular session."""
        return self._calendar.latest_completed_session(self._utc_now())

    def _value_for(
        self,
        symbol: str,
        bars: Sequence[DailyCloseBar],
        session: CompletedTradingSession,
        captured_at: datetime,
    ) -> DailyCloseAnchorValue:
        if not bars:
            return self._missing_value(
                symbol,
                captured_at,
                "provider returned no daily bar for the expected completed session",
            )

        exact = tuple(
            bar for bar in bars if bar.trading_date == session.trading_date
        )
        if len(exact) != 1:
            selected = max(bars, key=lambda bar: bar.trading_date)
            return self._rejected_value(
                selected,
                "provider did not return exactly one bar for the expected completed date",
            )

        bar = exact[0]
        if bar.source != self._provider.provider_code:
            return self._rejected_value(bar, "provider provenance did not match")
        if bar.source_feed != self._provider.daily_close_feed:
            return self._rejected_value(bar, "provider feed provenance did not match")
        if bar.currency != "USD":
            return self._rejected_value(bar, "daily close currency must be USD")
        if bar.quality in {DailyCloseQuality.STALE, DailyCloseQuality.UNAVAILABLE}:
            return self._rejected_value(bar, "provider marked the daily close unusable")
        if bar.market_timestamp > captured_at or bar.observed_at > captured_at:
            return self._rejected_value(bar, "provider returned future-dated daily data")

        return DailyCloseAnchorValue(
            symbol=symbol,
            close=bar.close,
            trading_date=bar.trading_date,
            market_timestamp=bar.market_timestamp.astimezone(UTC),
            observed_at=bar.observed_at.astimezone(UTC),
            source=bar.source,
            source_feed=bar.source_feed,
            currency=bar.currency,
            quality=bar.quality,
            status=DailyCloseValueStatus.AVAILABLE,
            message="accepted completed regular-session daily close",
        )

    def _missing_value(
        self, symbol: str, observed_at: datetime, message: str
    ) -> DailyCloseAnchorValue:
        return DailyCloseAnchorValue(
            symbol=symbol,
            close=None,
            trading_date=None,
            market_timestamp=None,
            observed_at=observed_at,
            source=self._provider.provider_code,
            source_feed=self._provider.daily_close_feed,
            currency="USD",
            quality=DailyCloseQuality.UNAVAILABLE,
            status=DailyCloseValueStatus.MISSING,
            message=message,
        )

    @staticmethod
    def _rejected_value(bar: DailyCloseBar, message: str) -> DailyCloseAnchorValue:
        return DailyCloseAnchorValue(
            symbol=bar.symbol,
            close=bar.close,
            trading_date=bar.trading_date,
            market_timestamp=bar.market_timestamp,
            observed_at=bar.observed_at,
            source=bar.source,
            source_feed=bar.source_feed,
            currency=bar.currency,
            quality=DailyCloseQuality.STALE,
            status=DailyCloseValueStatus.REJECTED,
            message=message,
        )

    def _store(
        self,
        relationship_id: str,
        session: CompletedTradingSession,
        underlying: DailyCloseAnchorValue,
        leveraged_product: DailyCloseAnchorValue,
        signed_leverage: Decimal,
        captured_at: datetime,
    ) -> DailyCloseAnchorPersistenceResult:
        available_count = sum(
            value.status == DailyCloseValueStatus.AVAILABLE
            for value in (underlying, leveraged_product)
        )
        status = (
            DailyCloseAnchorStatus.COMPLETE
            if available_count == 2
            else DailyCloseAnchorStatus.PARTIAL
            if available_count == 1
            else DailyCloseAnchorStatus.UNAVAILABLE
        )
        provenance = {
            (value.source, value.source_feed)
            for value in (underlying, leveraged_product)
            if value.status == DailyCloseValueStatus.AVAILABLE
        }
        provider = self._provider.provider_code
        source_feed = self._provider.daily_close_feed
        if len(provenance) == 1:
            provider, source_feed = next(iter(provenance))
        anchor = DailyCloseAnchor(
            id="pending",
            relationship_id=relationship_id,
            trading_date=session.trading_date,
            status=status,
            version=0,
            underlying=underlying,
            leveraged_product=leveraged_product,
            session_closed_at=session.closed_at.astimezone(UTC),
            captured_at=captured_at,
            provider=provider,
            source_feed=source_feed,
            signed_leverage=signed_leverage,
            created_at=captured_at,
        )
        if anchor.status != DailyCloseAnchorStatus.COMPLETE:
            return DailyCloseAnchorPersistenceResult(
                anchor=anchor,
                outcome=AnchorPersistenceOutcome.NOT_PERSISTED,
            )
        return self._repository.save(anchor)

    def _utc_now(self) -> datetime:
        timestamp = self._now()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("current time must be timezone-aware")
        return timestamp.astimezone(UTC)

    @staticmethod
    def _normalize_pair(underlying: str, leveraged: str) -> tuple[str, str]:
        pair = (underlying.strip().upper(), leveraged.strip().upper())
        if not all(pair) or pair[0] == pair[1]:
            raise ValueError("daily close capture requires two different symbols")
        if any(len(symbol) > 16 for symbol in pair):
            raise ValueError("symbol length cannot exceed 16 characters")
        return pair
