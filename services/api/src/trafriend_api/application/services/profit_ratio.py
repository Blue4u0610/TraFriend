from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import Callable, Optional, Sequence, Tuple
from uuid import uuid4

from trafriend_api.application.ports.daily_price import DailyPriceRepository
from trafriend_api.application.ports.profit_ratio import (
    ProfitRatioCaptureProvider,
    ProfitRatioPersistenceOutcome,
    ProfitRatioRepository,
    ProfitRatioSessionCalendar,
)
from trafriend_api.domain.errors import MarketDataProviderError, ResourceNotFoundError
from trafriend_api.domain.models import ProfitRatioMethodology
from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioCaptureInput,
    ProfitRatioConflictError,
    ProfitRatioObservation,
    ProfitRatioPhase,
    ProfitRatioRecord,
    ProfitRatioSession,
    ProfitRatioStatus,
    calculate_endpoint,
)

METHODOLOGY = ProfitRatioMethodology(
    id="CHIP_TURNOVER",
    version="1",
    display_name="TraFriend experimental turnover-cost estimate",
)


@dataclass(frozen=True)
class ProfitRatioDailyRow:
    trading_date: date
    open_ratio: Optional[Decimal]
    close_ratio: Optional[Decimal]
    open_price: Optional[Decimal]
    close_price: Optional[Decimal]
    price_change_return: Optional[Decimal]
    ratio_change: Optional[Decimal]
    open_observed_at: Optional[datetime]
    close_observed_at: Optional[datetime]
    quality: str
    status: str
    open_reason_code: Optional[str]
    close_reason_code: Optional[str]
    open_market_timestamp: Optional[datetime]
    close_market_timestamp: Optional[datetime]
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    price_status: str = "NOT_CAPTURED"
    price_provider: Optional[str] = None
    price_source_feed: Optional[str] = None
    price_observed_at: Optional[datetime] = None
    price_market_timestamp: Optional[datetime] = None
    price_quality: Optional[str] = None
    price_adjustment: Optional[str] = None
    price_scope: Optional[str] = None


@dataclass(frozen=True)
class ProfitRatioGap:
    trading_date: date
    phase: ProfitRatioPhase
    reason_code: str


@dataclass(frozen=True)
class ProfitRatioDailyHistory:
    symbol: str
    instrument_id: str
    methodology: ProfitRatioMethodology
    provider: str
    timezone: str
    as_of: datetime
    status: str
    rows: Tuple[ProfitRatioDailyRow, ...]
    gaps: Tuple[ProfitRatioGap, ...]


@dataclass(frozen=True)
class ProfitRatioCaptureItem:
    symbol: str
    outcome: str
    reason_code: str = ""


@dataclass(frozen=True)
class ProfitRatioCaptureReport:
    trading_date: date
    phase: ProfitRatioPhase
    status: str
    inserted: int = 0
    existing: int = 0
    upgraded: int = 0
    data_insufficient: int = 0
    unavailable: int = 0
    conflicts: int = 0
    results: Tuple[ProfitRatioCaptureItem, ...] = ()


class ProfitRatioService:
    """Finite endpoint capture and database-only QQQ constituent chart reads."""

    def __init__(
        self,
        repository: ProfitRatioRepository,
        calendar: ProfitRatioSessionCalendar,
        provider: Optional[ProfitRatioCaptureProvider] = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        publication_delay: timedelta = timedelta(minutes=20),
        price_repository: Optional[DailyPriceRepository] = None,
    ) -> None:
        if publication_delay < timedelta(0):
            raise ValueError("publication delay cannot be negative")
        self._repository = repository
        self._calendar = calendar
        self._provider = provider
        self._now = now
        self._publication_delay = publication_delay
        self._price_repository = price_repository

    def search(self, query: str, limit: int = 25) -> Sequence[NasdaqConstituent]:
        query = query.strip().upper()
        if len(query) > 64 or not 1 <= limit <= 25:
            raise ValueError("search query or limit is out of range")
        matches = [
            item
            for item in self._repository.list_constituents()
            if query in item.symbol or query in item.name.upper()
        ]
        return tuple(
            sorted(
                matches,
                key=lambda item: (
                    item.symbol != query,
                    not item.symbol.startswith(query),
                    item.symbol,
                ),
            )[:limit]
        )

    def daily(self, symbol: str, start: date, end: date) -> ProfitRatioDailyHistory:
        if end < start or (end - start).days > 366:
            raise ValueError("daily history supports ordered ranges up to 366 days")
        constituent = self._constituent(symbol)
        now = self._utc_now()
        records = self._repository.history(constituent.instrument_id, start, end)
        price_bars = (
            self._price_repository.history(constituent.instrument_id, start, end)
            if self._price_repository is not None
            else ()
        )
        by_price_date = {
            bar.trading_date: bar
            for bar in price_bars
            if bar.session_closed_at <= now and bar.observed_at <= now
        }
        by_phase = {
            (item.observation.trading_date, item.observation.phase): item
            for item in records
            if item.observation.methodology_key == METHODOLOGY.id
            and item.observation.methodology_version == METHODOLOGY.version
        }
        rows: list[ProfitRatioDailyRow] = []
        gaps: list[ProfitRatioGap] = []
        for session in self._calendar.sessions(start, end):
            if session.opened_at > now:
                continue
            opening = by_phase.get((session.trading_date, ProfitRatioPhase.OPEN))
            closing = by_phase.get((session.trading_date, ProfitRatioPhase.CLOSE))
            row = self._row(session, opening, closing, now, self._publication_delay)
            bar = by_price_date.get(session.trading_date)
            if bar is not None:
                row = replace(
                    row,
                    open_price=bar.open,
                    high_price=bar.high,
                    low_price=bar.low,
                    close_price=bar.close,
                    price_change_return=bar.price_change_return,
                    price_status="COMPLETE",
                    price_provider=bar.provider,
                    price_source_feed=bar.source_feed,
                    price_observed_at=bar.observed_at,
                    price_market_timestamp=bar.market_timestamp,
                    price_quality=bar.quality,
                    price_adjustment=bar.adjustment,
                    price_scope=bar.price_scope,
                )
            rows.append(row)
            if row.status == "PROVENANCE_MISMATCH":
                gaps.append(
                    ProfitRatioGap(
                        session.trading_date, ProfitRatioPhase.CLOSE, "PROVENANCE_MISMATCH"
                    )
                )
            for phase, record in (
                (ProfitRatioPhase.OPEN, opening),
                (ProfitRatioPhase.CLOSE, closing),
            ):
                if record is None or record.observation.ratio is None:
                    reason = (
                        record.observation.reason_code
                        if record is not None
                        else "NOT_DUE"
                        if session.instant(phase) + self._publication_delay > now
                        else "NOT_CAPTURED"
                    )
                    gaps.append(ProfitRatioGap(session.trading_date, phase, reason))
        providers = {item.observation.provider for item in records} | {
            bar.provider for bar in by_price_date.values()
        }
        has_prices = any(row.open_price is not None or row.close_price is not None for row in rows)
        has_ratios = any(row.open_ratio is not None or row.close_ratio is not None for row in rows)
        status = (
            "EMPTY"
            if not has_prices
            else "DATA_INSUFFICIENT"
            if not has_ratios
            else "PARTIAL"
            if gaps
            else "COMPLETE"
        )
        return ProfitRatioDailyHistory(
            symbol=constituent.symbol,
            instrument_id=constituent.instrument_id,
            methodology=METHODOLOGY,
            provider=next(iter(providers))
            if len(providers) == 1
            else "mixed"
            if providers
            else "none",
            timezone="America/New_York",
            as_of=now,
            status=status,
            rows=tuple(rows),
            gaps=tuple(gaps),
        )

    def capture(
        self,
        trading_date: date,
        phase: ProfitRatioPhase,
        symbols: Optional[Sequence[str]] = None,
        retry_insufficient: bool = False,
    ) -> ProfitRatioCaptureReport:
        session = self._calendar.session(trading_date)
        now = self._utc_now()
        if session.instant(phase) + self._publication_delay > now:
            return ProfitRatioCaptureReport(trading_date, phase, "NOT_DUE")
        members = list(self._repository.list_constituents())
        if symbols is not None:
            members = [self._constituent(symbol) for symbol in dict.fromkeys(symbols)]
        items: list[ProfitRatioCaptureItem] = []
        pending: list[NasdaqConstituent] = []
        insufficient = 0
        for member in members:
            existing = self._repository.latest(member.instrument_id, trading_date, phase)
            if existing is not None and (
                existing.observation.ratio is not None or not retry_insufficient
            ):
                items.append(ProfitRatioCaptureItem(member.symbol, "EXISTING"))
                insufficient += int(existing.observation.ratio is None)
            else:
                pending.append(member)
        if pending:
            try:
                if self._provider is None:
                    raise MarketDataProviderError("capture provider is not configured")
                inputs = self._provider.get_capture_inputs(
                    [member.symbol for member in pending], session, phase
                )
            except MarketDataProviderError:
                items.extend(
                    ProfitRatioCaptureItem(member.symbol, "UNAVAILABLE", "PROVIDER_FAILURE")
                    for member in pending
                )
            else:
                captured_at = self._utc_now()
                for member in pending:
                    matches = [item for item in inputs if item.price.symbol == member.symbol]
                    if len(matches) != 1:
                        items.append(
                            ProfitRatioCaptureItem(
                                member.symbol, "UNAVAILABLE", "EXPECTED_PRICE_MISSING_OR_DUPLICATE"
                            )
                        )
                        continue
                    capture_input = matches[0]
                    if not self._valid_input(capture_input, member, session, phase, captured_at):
                        items.append(
                            ProfitRatioCaptureItem(
                                member.symbol, "UNAVAILABLE", "INVALID_SESSION_PRICE"
                            )
                        )
                        continue
                    model = calculate_endpoint(capture_input, session)
                    observation = ProfitRatioObservation(
                        id=str(uuid4()),
                        instrument_id=member.instrument_id,
                        symbol=member.symbol,
                        trading_date=trading_date,
                        phase=phase,
                        ratio=model.ratio,
                        market_timestamp=session.instant(phase),
                        observed_at=captured_at,
                        provider=capture_input.price.provider,
                        source_feed=capture_input.price.source_feed,
                        quality=capture_input.quality,
                        status=ProfitRatioStatus.ESTIMATED
                        if model.ratio is not None
                        else ProfitRatioStatus.DATA_INSUFFICIENT,
                        reason_code=model.reason_code,
                    )
                    try:
                        saved = self._repository.save(
                            ProfitRatioRecord(
                                observation=observation,
                                price=capture_input.price,
                            )
                        )
                    except ProfitRatioConflictError:
                        items.append(
                            ProfitRatioCaptureItem(
                                member.symbol, "CONFLICT", "IMMUTABLE_VALUES_CONFLICT"
                            )
                        )
                    else:
                        insufficient += int(saved.record.observation.ratio is None)
                        items.append(
                            ProfitRatioCaptureItem(
                                member.symbol,
                                saved.outcome.value,
                                model.reason_code,
                            )
                        )
        unavailable = sum(item.outcome == "UNAVAILABLE" for item in items)
        conflicts = sum(item.outcome == "CONFLICT" for item in items)
        return ProfitRatioCaptureReport(
            trading_date=trading_date,
            phase=phase,
            status="PARTIAL_RETRYABLE"
            if unavailable
            else "CONFLICT"
            if conflicts
            else "DATA_INSUFFICIENT"
            if insufficient
            else "COMPLETE"
            if items
            else "EMPTY_UNIVERSE",
            inserted=sum(item.outcome == ProfitRatioPersistenceOutcome.INSERTED for item in items),
            existing=sum(item.outcome == ProfitRatioPersistenceOutcome.EXISTING for item in items),
            upgraded=sum(item.outcome == ProfitRatioPersistenceOutcome.UPGRADED for item in items),
            data_insufficient=insufficient,
            unavailable=unavailable,
            conflicts=conflicts,
            results=tuple(items),
        )

    def _constituent(self, symbol: str) -> NasdaqConstituent:
        normalized = symbol.strip().upper()
        for item in self._repository.list_constituents():
            if item.symbol == normalized:
                return item
        raise ResourceNotFoundError("symbol is not in the current QQQ constituent snapshot")

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware instant")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _valid_input(
        inputs: ProfitRatioCaptureInput,
        member: NasdaqConstituent,
        session: ProfitRatioSession,
        phase: ProfitRatioPhase,
        now: datetime,
    ) -> bool:
        price = inputs.price
        return (
            price.instrument_id == member.instrument_id
            and price.symbol == member.symbol
            and price.trading_date == session.trading_date
            and price.phase == phase
            and price.market_timestamp == session.instant(phase)
            and price.observed_at <= now
            and (inputs.float_snapshot is None or inputs.float_snapshot.observed_at <= now)
            and inputs.quality in {"REALTIME", "DELAYED", "MOCK"}
            and (price.provider == "mock" or price.source_feed == "sip")
        )

    @staticmethod
    def _row(
        session: ProfitRatioSession,
        opening: Optional[ProfitRatioRecord],
        closing: Optional[ProfitRatioRecord],
        now: datetime,
        publication_delay: timedelta,
    ) -> ProfitRatioDailyRow:
        open_ratio = opening.observation.ratio if opening else None
        close_ratio = closing.observation.ratio if closing else None
        same_provenance = (
            opening is not None
            and closing is not None
            and (
                opening.observation.provider,
                opening.observation.source_feed,
                opening.observation.methodology_key,
                opening.observation.methodology_version,
                opening.observation.quality,
            )
            == (
                closing.observation.provider,
                closing.observation.source_feed,
                closing.observation.methodology_key,
                closing.observation.methodology_version,
                closing.observation.quality,
            )
        )
        with localcontext() as context:
            context.prec = 40
            price_change = (
                closing.price.price / closing.price.previous_close - 1
                if closing and closing.price.previous_close is not None
                else None
            )
            ratio_change = (
                close_ratio - open_ratio
                if close_ratio is not None and open_ratio is not None and same_provenance
                else None
            )
        qualities = {item.observation.quality for item in (opening, closing) if item is not None}
        latest_price_context = closing or opening
        return ProfitRatioDailyRow(
            trading_date=session.trading_date,
            open_ratio=open_ratio,
            close_ratio=close_ratio,
            open_price=opening.price.price if opening else None,
            close_price=closing.price.price if closing else None,
            price_change_return=price_change,
            ratio_change=ratio_change,
            open_observed_at=opening.observation.observed_at if opening else None,
            close_observed_at=closing.observation.observed_at if closing else None,
            quality=next(iter(qualities))
            if len(qualities) == 1
            else "MIXED"
            if qualities
            else "UNAVAILABLE",
            status="PROVENANCE_MISMATCH"
            if opening and closing and not same_provenance
            else "COMPLETE"
            if open_ratio is not None and close_ratio is not None
            else "PARTIAL"
            if open_ratio is not None or close_ratio is not None
            else "DATA_INSUFFICIENT"
            if opening or closing
            else "NOT_CAPTURED",
            open_reason_code=opening.observation.reason_code
            if opening
            else "NOT_DUE"
            if session.opened_at + publication_delay > now
            else "NOT_CAPTURED",
            close_reason_code=closing.observation.reason_code
            if closing
            else "NOT_DUE"
            if session.closed_at + publication_delay > now
            else "NOT_CAPTURED",
            open_market_timestamp=opening.observation.market_timestamp if opening else None,
            close_market_timestamp=closing.observation.market_timestamp if closing else None,
            price_status="PARTIAL"
            if latest_price_context
            else "NOT_DUE"
            if session.closed_at + publication_delay > now
            else "NOT_CAPTURED",
            price_provider=latest_price_context.price.provider if latest_price_context else None,
            price_source_feed=latest_price_context.price.source_feed
            if latest_price_context
            else None,
            price_observed_at=latest_price_context.price.observed_at
            if latest_price_context
            else None,
            price_market_timestamp=latest_price_context.price.market_timestamp
            if latest_price_context
            else None,
            price_quality=latest_price_context.observation.quality
            if latest_price_context
            else None,
            price_adjustment="raw" if latest_price_context else None,
            price_scope="ENDPOINT_CONTEXT_ONLY" if latest_price_context else None,
        )
