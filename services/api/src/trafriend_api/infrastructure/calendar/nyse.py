from datetime import date, datetime, timezone

import exchange_calendars

from trafriend_api.application.ports.daily_close import CompletedSessionCalendar
from trafriend_api.application.ports.overnight_market_data import TradingCalendar
from trafriend_api.domain.daily_close import CompletedTradingSession

UTC = timezone.utc


class NyseTradingCalendar(TradingCalendar, CompletedSessionCalendar):
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
