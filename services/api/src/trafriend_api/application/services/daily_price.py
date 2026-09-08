from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from trafriend_api.application.ports.daily_price import DailyPriceProvider, DailyPriceRepository
from trafriend_api.application.ports.profit_ratio import (
    ProfitRatioRepository,
    ProfitRatioSessionCalendar,
)
from trafriend_api.domain.daily_price import DailyPriceBar, DailyPriceConflictError
from trafriend_api.domain.errors import MarketDataProviderError, ResourceNotFoundError
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent, ProfitRatioSession


@dataclass(frozen=True)
class DailyPriceCaptureItem:
    symbol: str
    trading_date: date
    outcome: str
    reason_code: str = ""


@dataclass(frozen=True)
class DailyPriceCaptureReport:
    start: date
    end: date
    status: str
    symbols: int
    sessions: int
    inserted: int
    existing: int
    unavailable: int
    conflicts: int
    results: Tuple[DailyPriceCaptureItem, ...]


class DailyPriceCaptureService:
    """Bounded provider capture independent of ratios and leveraged products."""

    def __init__(
        self,
        catalog: ProfitRatioRepository,
        repository: DailyPriceRepository,
        provider: DailyPriceProvider,
        calendar: ProfitRatioSessionCalendar,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        publication_delay: timedelta = timedelta(minutes=20),
    ) -> None:
        if publication_delay < timedelta(0):
            raise ValueError("publication delay cannot be negative")
        self._catalog = catalog
        self._repository = repository
        self._provider = provider
        self._calendar = calendar
        self._now = now
        self._publication_delay = publication_delay

    def capture(
        self, start: date, end: date, symbols: Optional[Sequence[str]] = None
    ) -> DailyPriceCaptureReport:
        if end < start or (end - start).days > 100:
            raise ValueError("daily capture requires an ordered range up to 100 days")
        now = self._utc_now()
        if end > now.astimezone(ZoneInfo("America/New_York")).date():
            raise ValueError("daily capture cannot request future dates")
        members = self._catalog.list_constituents()
        if symbols is not None:
            requested = set(symbol.strip().upper() for symbol in symbols)
            if requested - {member.symbol for member in members}:
                raise ResourceNotFoundError("symbol is not in the current QQQ constituent snapshot")
            members = tuple(member for member in members if member.symbol in requested)
        sessions = tuple(
            session
            for session in self._calendar.sessions(start, end)
            if session.closed_at + self._publication_delay <= now
        )
        results: list[DailyPriceCaptureItem] = []
        pending: dict[tuple[str, date], tuple[NasdaqConstituent, ProfitRatioSession]] = {}
        for member in members:
            stored_dates = {
                bar.trading_date
                for bar in self._repository.history(member.instrument_id, start, end)
            }
            for session in sessions:
                if session.trading_date in stored_dates:
                    results.append(
                        DailyPriceCaptureItem(member.symbol, session.trading_date, "EXISTING")
                    )
                else:
                    pending[(member.instrument_id, session.trading_date)] = (member, session)
        if pending:
            pending_symbols = sorted({member.symbol for member, _session in pending.values()})
            pending_dates = {session.trading_date for _member, session in pending.values()}
            try:
                bars = self._provider.get_daily_price_bars(
                    pending_symbols,
                    tuple(session for session in sessions if session.trading_date in pending_dates),
                )
            except MarketDataProviderError:
                results.extend(
                    DailyPriceCaptureItem(
                        member.symbol, session.trading_date, "UNAVAILABLE", "PROVIDER_FAILURE"
                    )
                    for member, session in pending.values()
                )
            else:
                observed_at = self._utc_now()
                by_identity: dict[tuple[str, date], list[DailyPriceBar]] = {}
                for bar in bars:
                    by_identity.setdefault((bar.instrument_id, bar.trading_date), []).append(bar)
                for key, (member, session) in pending.items():
                    candidates = by_identity.get(key, [])
                    if len(candidates) != 1 or not self._valid(
                        candidates[0], member, session, observed_at
                    ):
                        results.append(
                            DailyPriceCaptureItem(
                                member.symbol,
                                session.trading_date,
                                "UNAVAILABLE",
                                "EXPECTED_DAILY_BAR_MISSING_OR_INVALID",
                            )
                        )
                        continue
                    try:
                        outcome = self._repository.save(candidates[0]).outcome.value
                    except DailyPriceConflictError:
                        results.append(
                            DailyPriceCaptureItem(
                                member.symbol,
                                session.trading_date,
                                "CONFLICT",
                                "IMMUTABLE_VALUES_CONFLICT",
                            )
                        )
                    else:
                        results.append(
                            DailyPriceCaptureItem(member.symbol, session.trading_date, outcome)
                        )
        unavailable = sum(item.outcome == "UNAVAILABLE" for item in results)
        conflicts = sum(item.outcome == "CONFLICT" for item in results)
        return DailyPriceCaptureReport(
            start=start,
            end=end,
            symbols=len(members),
            sessions=len(sessions),
            status="EMPTY_UNIVERSE"
            if not members
            else "NOT_DUE"
            if not sessions
            else "CONFLICT"
            if conflicts
            else "PARTIAL_RETRYABLE"
            if unavailable
            else "COMPLETE",
            inserted=sum(item.outcome == "INSERTED" for item in results),
            existing=sum(item.outcome == "EXISTING" for item in results),
            unavailable=unavailable,
            conflicts=conflicts,
            results=tuple(results),
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capture clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _valid(
        bar: DailyPriceBar,
        member: NasdaqConstituent,
        session: ProfitRatioSession,
        now: datetime,
    ) -> bool:
        market_local = bar.market_timestamp.astimezone(ZoneInfo("America/New_York"))
        return (
            bar.instrument_id == member.instrument_id
            and bar.symbol == member.symbol
            and bar.trading_date == session.trading_date
            and bar.session_opened_at == session.opened_at
            and bar.session_closed_at == session.closed_at
            and bar.observed_at <= now
            and market_local.date() == session.trading_date
            and (
                market_local.hour,
                market_local.minute,
                market_local.second,
                market_local.microsecond,
            )
            == (0, 0, 0, 0)
            and (bar.provider == "mock" or bar.source_feed == "sip")
        )
