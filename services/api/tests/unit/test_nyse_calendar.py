from datetime import date

from trafriend_api.infrastructure.calendar import NyseTradingCalendar


def test_nyse_calendar_rejects_weekends_and_market_holidays() -> None:
    calendar = NyseTradingCalendar()

    assert not calendar.is_trading_day(date(2026, 9, 6))
    assert not calendar.is_trading_day(date(2026, 9, 7))
    assert calendar.is_trading_day(date(2026, 9, 8))

