from datetime import date

import exchange_calendars

from trafriend_api.application.ports.overnight_market_data import TradingCalendar


class NyseTradingCalendar(TradingCalendar):
    """NYSE session calendar adapter, including holidays and special closures."""

    def __init__(self) -> None:
        self._calendar = exchange_calendars.get_calendar("XNYS")

    def is_trading_day(self, trading_date: date) -> bool:
        return bool(self._calendar.is_session(trading_date.isoformat()))

