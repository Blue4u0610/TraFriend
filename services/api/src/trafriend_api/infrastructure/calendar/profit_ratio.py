from datetime import date, timezone

import exchange_calendars

from trafriend_api.application.ports.profit_ratio import ProfitRatioSessionCalendar
from trafriend_api.domain.profit_ratio_daily import (
    ProfitRatioCalendarRangeError,
    ProfitRatioSession,
)


class ProfitRatioExchangeCalendar(ProfitRatioSessionCalendar):
    """US equity regular-session boundaries shared by Nasdaq and NYSE stocks.

    XNYS supplies the US equity holiday/early-close schedule. This adapter does
    not use an overnight session or the calculator's completed-close selector.
    """

    def __init__(self) -> None:
        self._calendar = exchange_calendars.get_calendar("XNYS")

    def session(self, trading_date: date) -> ProfitRatioSession:
        self._validate_range(trading_date, trading_date)
        label = trading_date.isoformat()
        if not self._calendar.is_session(label):
            raise ValueError("requested date is not a US equity trading session")
        return ProfitRatioSession(
            trading_date=trading_date,
            opened_at=self._calendar.session_open(label).to_pydatetime().astimezone(timezone.utc),
            closed_at=self._calendar.session_close(label).to_pydatetime().astimezone(timezone.utc),
            previous_trading_date=self._calendar.previous_session(label).date(),
        )

    def sessions(self, start: date, end: date) -> tuple[ProfitRatioSession, ...]:
        if end < start:
            raise ValueError("end must be on or after start")
        self._validate_range(start, end)
        return tuple(
            self.session(label.date())
            for label in self._calendar.sessions_in_range(start.isoformat(), end.isoformat())
        )

    def _validate_range(self, start: date, end: date) -> None:
        # A usable phase also requires its preceding session. Compare Python
        # dates before pandas parses inputs outside its timestamp range.
        first_usable = self._calendar.sessions[1].date()
        last_usable = self._calendar.last_session.date()
        if start < first_usable or end > last_usable:
            raise ProfitRatioCalendarRangeError(
                "requested dates are outside supported exchange-calendar coverage"
            )
