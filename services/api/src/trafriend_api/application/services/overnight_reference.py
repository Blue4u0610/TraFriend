from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, Iterable, Sequence, Tuple
from zoneinfo import ZoneInfo

from trafriend_api.application.ports.overnight_market_data import (
    OvernightMarketDataProvider,
    OvernightReferenceRepository,
    TradingCalendar,
)
from trafriend_api.domain.errors import MarketDataProviderError, OvernightSessionError
from trafriend_api.domain.overnight import (
    CaptureStatus,
    DataQuality,
    OvernightBar,
    OvernightQuote,
    OvernightReferenceCapture,
    OvernightReferenceValue,
    PriceBasis,
    ReferenceStatus,
    ReferenceType,
)

UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")


class OvernightReferenceService:
    """Captures auditable overnight references without provider-specific behavior."""

    def __init__(
        self,
        provider: OvernightMarketDataProvider,
        calendar: TradingCalendar,
        repository: OvernightReferenceRepository,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        open_search_window: timedelta = timedelta(minutes=15),
        snapshot_time: time = time(20, 5),
        realtime_snapshot_tolerance: timedelta = timedelta(seconds=90),
        delayed_snapshot_tolerance: timedelta = timedelta(minutes=20),
        max_snapshot_skew: timedelta = timedelta(seconds=5),
    ) -> None:
        if not provider.capabilities.true_overnight:
            raise ValueError("provider does not declare true overnight support")
        self._provider = provider
        self._calendar = calendar
        self._repository = repository
        self._now = now
        self._open_search_window = open_search_window
        self._snapshot_time = snapshot_time
        self._realtime_snapshot_tolerance = realtime_snapshot_tolerance
        self._delayed_snapshot_tolerance = delayed_snapshot_tolerance
        self._max_snapshot_skew = max_snapshot_skew

    def session_window(self, trading_date: date) -> Tuple[datetime, datetime]:
        if not self._calendar.is_trading_day(trading_date):
            raise OvernightSessionError(
                f"{trading_date.isoformat()} is not an exchange trading day"
            )
        session_start = datetime.combine(
            trading_date - timedelta(days=1), time(20, 0), tzinfo=EASTERN
        )
        session_end = datetime.combine(trading_date, time(4, 0), tzinfo=EASTERN)
        return session_start.astimezone(UTC), session_end.astimezone(UTC)

    def trading_date_for(self, timestamp: datetime) -> date:
        self._require_aware(timestamp)
        local_timestamp = timestamp.astimezone(EASTERN)
        local_time = local_timestamp.timetz().replace(tzinfo=None)
        if local_time >= time(20, 0):
            trading_date = local_timestamp.date() + timedelta(days=1)
        elif local_time < time(4, 0):
            trading_date = local_timestamp.date()
        else:
            raise OvernightSessionError("timestamp is outside the overnight session")
        if not self._calendar.is_trading_day(trading_date):
            raise OvernightSessionError(
                "timestamp maps to a non-trading day; no overnight session is available"
            )
        return trading_date

    def snapshot_timestamp(self, trading_date: date) -> datetime:
        session_start, _ = self.session_window(trading_date)
        local_date = session_start.astimezone(EASTERN).date()
        return datetime.combine(
            local_date, self._snapshot_time, tzinfo=EASTERN
        ).astimezone(UTC)

    def capture_open(
        self, symbols: Sequence[str], trading_date: date
    ) -> OvernightReferenceCapture:
        normalized = self._normalize_symbols(symbols)
        session_start, session_end = self.session_window(trading_date)
        search_end = min(session_start + self._open_search_window, session_end)
        try:
            bars = self._provider.get_overnight_bars(
                normalized, session_start, search_end, "1Min"
            )
        except MarketDataProviderError as exc:
            return self._store_provider_failure(
                normalized, trading_date, ReferenceType.OVERNIGHT_OPEN, exc
            )

        by_symbol: Dict[str, list[OvernightBar]] = {symbol: [] for symbol in normalized}
        for bar in bars:
            symbol = bar.symbol.upper()
            if symbol in by_symbol and session_start <= bar.starts_at < search_end:
                by_symbol[symbol].append(bar)

        values = []
        for symbol in normalized:
            candidates = sorted(by_symbol[symbol], key=lambda bar: bar.starts_at)
            if not candidates:
                values.append(
                    self._missing_value(
                        symbol,
                        trading_date,
                        ReferenceType.OVERNIGHT_OPEN,
                        "no valid one-minute overnight bar in the opening search window",
                    )
                )
                continue
            bar = candidates[0]
            rejected = bar.quality in {DataQuality.STALE, DataQuality.UNAVAILABLE}
            values.append(
                OvernightReferenceValue(
                    symbol=symbol,
                    trading_date=trading_date,
                    price=bar.open_price,
                    reference_type=ReferenceType.OVERNIGHT_OPEN,
                    source=bar.source,
                    source_feed=bar.source_feed,
                    observed_at=bar.observed_at.astimezone(UTC),
                    market_timestamp=bar.starts_at.astimezone(UTC),
                    quality=bar.quality,
                    status=(
                        ReferenceStatus.REJECTED
                        if rejected
                        else ReferenceStatus.AVAILABLE
                    ),
                    price_basis=PriceBasis.BAR_OPEN,
                    message=(
                        "provider marked the selected opening bar unusable"
                        if rejected
                        else "selected first valid one-minute bar in opening search window"
                    ),
                )
            )
        values = list(self._reject_mixed_provenance(values))
        return self._store_capture(
            trading_date, ReferenceType.OVERNIGHT_OPEN, tuple(values)
        )

    def capture_snapshot(
        self, symbols: Sequence[str], trading_date: date
    ) -> OvernightReferenceCapture:
        normalized = self._normalize_symbols(symbols)
        session_start, session_end = self.session_window(trading_date)
        target = self.snapshot_timestamp(trading_date)
        try:
            quotes = self._provider.get_overnight_snapshot(normalized, target)
        except MarketDataProviderError as exc:
            return self._store_provider_failure(
                normalized, trading_date, ReferenceType.OVERNIGHT_SNAPSHOT, exc
            )

        by_symbol = {quote.symbol.upper(): quote for quote in quotes}
        values = []
        for symbol in normalized:
            quote = by_symbol.get(symbol)
            if quote is None:
                values.append(
                    self._missing_value(
                        symbol,
                        trading_date,
                        ReferenceType.OVERNIGHT_SNAPSHOT,
                        "provider returned no overnight quote",
                    )
                )
                continue
            values.append(
                self._snapshot_value(
                    quote, trading_date, target, session_start, session_end
                )
            )

        values = list(self._reject_mixed_provenance(values))
        values = list(self._reject_out_of_sync(values))
        return self._store_capture(
            trading_date, ReferenceType.OVERNIGHT_SNAPSHOT, tuple(values)
        )

    def _snapshot_value(
        self,
        quote: OvernightQuote,
        trading_date: date,
        target: datetime,
        session_start: datetime,
        session_end: datetime,
    ) -> OvernightReferenceValue:
        market_timestamp = quote.market_timestamp.astimezone(UTC)
        tolerance = (
            self._delayed_snapshot_tolerance
            if quote.quality == DataQuality.DELAYED
            else self._realtime_snapshot_tolerance
        )
        is_stale = (
            quote.quality in {DataQuality.STALE, DataQuality.UNAVAILABLE}
            or not session_start <= market_timestamp < session_end
            or abs(market_timestamp - target) > tolerance
        )
        return OvernightReferenceValue(
            symbol=quote.symbol.upper(),
            trading_date=trading_date,
            price=quote.price,
            reference_type=ReferenceType.OVERNIGHT_SNAPSHOT,
            source=quote.source,
            source_feed=quote.source_feed,
            observed_at=quote.observed_at.astimezone(UTC),
            market_timestamp=market_timestamp,
            quality=DataQuality.STALE if is_stale else quote.quality,
            status=ReferenceStatus.REJECTED if is_stale else ReferenceStatus.AVAILABLE,
            price_basis=quote.price_basis,
            message=(
                "quote is outside the snapshot freshness window"
                if is_stale
                else "quote midpoint accepted within time and synchronization tolerances"
            ),
        )

    def _reject_mixed_provenance(
        self, values: Iterable[OvernightReferenceValue]
    ) -> Tuple[OvernightReferenceValue, ...]:
        result = tuple(values)
        available = tuple(
            value for value in result if value.status == ReferenceStatus.AVAILABLE
        )
        provenance = {(value.source, value.source_feed) for value in available}
        source_matches = all(
            value.source == self._provider.provider_code for value in available
        )
        if len(provenance) <= 1 and source_matches:
            return result
        return tuple(
            replace(
                value,
                quality=DataQuality.UNAVAILABLE,
                status=ReferenceStatus.REJECTED,
                message="capture contains mixed or unexpected provider provenance",
            )
            if value.status == ReferenceStatus.AVAILABLE
            else value
            for value in result
        )

    def _reject_out_of_sync(
        self, values: Iterable[OvernightReferenceValue]
    ) -> Tuple[OvernightReferenceValue, ...]:
        result = tuple(values)
        available = tuple(
            value
            for value in result
            if value.status == ReferenceStatus.AVAILABLE
            and value.market_timestamp is not None
        )
        if len(available) < 2:
            return result
        newest = max(value.market_timestamp for value in available if value.market_timestamp)
        oldest = min(value.market_timestamp for value in available if value.market_timestamp)
        if newest - oldest <= self._max_snapshot_skew:
            return result
        cutoff = newest - self._max_snapshot_skew
        return tuple(
            replace(
                value,
                quality=DataQuality.STALE,
                status=ReferenceStatus.REJECTED,
                message="quote timestamp is outside the synchronization tolerance",
            )
            if value.status == ReferenceStatus.AVAILABLE
            and value.market_timestamp is not None
            and value.market_timestamp < cutoff
            else value
            for value in result
        )

    def _store_provider_failure(
        self,
        symbols: Sequence[str],
        trading_date: date,
        reference_type: ReferenceType,
        error: MarketDataProviderError,
    ) -> OvernightReferenceCapture:
        values = tuple(
            self._missing_value(
                symbol,
                trading_date,
                reference_type,
                f"provider failure: {error.__class__.__name__}",
            )
            for symbol in symbols
        )
        return self._store_capture(trading_date, reference_type, values)

    def _missing_value(
        self,
        symbol: str,
        trading_date: date,
        reference_type: ReferenceType,
        message: str,
    ) -> OvernightReferenceValue:
        return OvernightReferenceValue(
            symbol=symbol,
            trading_date=trading_date,
            price=None,
            reference_type=reference_type,
            source=self._provider.provider_code,
            source_feed=self._provider.source_feed,
            observed_at=self._utc_now(),
            market_timestamp=None,
            quality=DataQuality.UNAVAILABLE,
            status=ReferenceStatus.MISSING,
            price_basis=(
                PriceBasis.BAR_OPEN
                if reference_type == ReferenceType.OVERNIGHT_OPEN
                else PriceBasis.QUOTE_MIDPOINT
            ),
            message=message,
        )

    def _store_capture(
        self,
        trading_date: date,
        reference_type: ReferenceType,
        values: Tuple[OvernightReferenceValue, ...],
    ) -> OvernightReferenceCapture:
        available_count = sum(
            value.status == ReferenceStatus.AVAILABLE for value in values
        )
        status = (
            CaptureStatus.COMPLETE
            if available_count == len(values)
            else CaptureStatus.UNAVAILABLE
            if available_count == 0
            else CaptureStatus.PARTIAL
        )
        captured_at = max(value.observed_at for value in values)
        observed_provenance = {
            (value.source, value.source_feed)
            for value in values
            if value.market_timestamp is not None
        }
        if len(observed_provenance) == 1:
            source, source_feed = next(iter(observed_provenance))
        else:
            source = self._provider.provider_code
            source_feed = self._provider.source_feed
        capture = OvernightReferenceCapture(
            id="pending",
            version=0,
            trading_date=trading_date,
            reference_type=reference_type,
            status=status,
            values=values,
            captured_at=captured_at,
            source=source,
            source_feed=source_feed,
        )
        return self._repository.save(capture)

    def _utc_now(self) -> datetime:
        timestamp = self._now()
        self._require_aware(timestamp)
        return timestamp.astimezone(UTC)

    @staticmethod
    def _normalize_symbols(symbols: Sequence[str]) -> Tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
        )
        if not normalized:
            raise ValueError("at least one symbol is required")
        if len(normalized) > 200:
            raise ValueError("at most 200 symbols may be captured together")
        if any(len(symbol) > 16 for symbol in normalized):
            raise ValueError("symbol length cannot exceed 16 characters")
        return normalized

    @staticmethod
    def _require_aware(timestamp: datetime) -> None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
