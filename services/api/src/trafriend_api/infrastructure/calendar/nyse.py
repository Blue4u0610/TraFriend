import calendar
from datetime import date, datetime, timezone

import exchange_calendars

from trafriend_api.application.ports.daily_close import CompletedSessionCalendar
from trafriend_api.application.ports.overnight_market_data import TradingCalendar
from trafriend_api.application.ports.ranking import RankingSessionCalendar
from trafriend_api.domain.daily_close import CompletedTradingSession

UTC = timezone.utc


class NyseTradingCalendar(
    TradingCalendar,
    CompletedSessionCalendar,
    RankingSessionCalendar,
):
    """NYSE session calendar adapter, including holidays and special closures."""

    def __init__(self) -> None:
        self._calendar = exchange_calendars.get_calendar("XNYS")

    def is_trading_day(self, trading_date: date) -> bool:
        return bool(self._calendar.is_session(trading_date.isoformat()))

    def latest_completed_session(
        self, timestamp: datetime
    ) -> CompletedTradingSession:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        instant = timestamp.astimezone(UTC)
        closed_at = self._calendar.previous_close(instant)
        session = self._calendar.minute_to_session(closed_at, direction="previous")
        return CompletedTradingSession(
            trading_date=session.date(),
            closed_at=closed_at.to_pydatetime().astimezone(UTC),
        )

    def completed_trading_dates_in_month(
        self, timestamp: datetime, year: int, month: int
    ) -> tuple[date, ...]:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        latest = self.latest_completed_session(timestamp).trading_date
        effective_end = min(month_end, latest)
        if effective_end < month_start:
            return ()
        sessions = self._calendar.sessions_in_range(
            month_start.isoformat(), effective_end.isoformat()
        )
        return tuple(session.date() for session in sessions)

    def trading_dates_in_month(self, year: int, month: int) -> tuple[date, ...]:
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        sessions = self._calendar.sessions_in_range(
            month_start.isoformat(), month_end.isoformat()
        )
        return tuple(session.date() for session in sessions)
