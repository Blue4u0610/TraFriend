from datetime import date, datetime
from zoneinfo import ZoneInfo

from trafriend_api.infrastructure.calendar import NyseTradingCalendar

EASTERN = ZoneInfo("America/New_York")


def test_nyse_calendar_rejects_weekends_and_market_holidays() -> None:
    calendar = NyseTradingCalendar()

    assert not calendar.is_trading_day(date(2026, 9, 6))
    assert not calendar.is_trading_day(date(2026, 9, 7))
    assert calendar.is_trading_day(date(2026, 9, 8))


def test_latest_completed_session_before_and_after_regular_close() -> None:
    calendar = NyseTradingCalendar()

    before = calendar.latest_completed_session(
        datetime(2026, 9, 4, 15, 59, tzinfo=EASTERN)
    )
    after = calendar.latest_completed_session(
        datetime(2026, 9, 4, 16, 1, tzinfo=EASTERN)
    )

    assert before.trading_date == date(2026, 9, 3)
    assert after.trading_date == date(2026, 9, 4)


def test_latest_completed_session_handles_weekend_and_holiday() -> None:
    calendar = NyseTradingCalendar()

    weekend = calendar.latest_completed_session(
        datetime(2026, 9, 5, 12, tzinfo=EASTERN)
    )
    labor_day = calendar.latest_completed_session(
        datetime(2026, 9, 7, 12, tzinfo=EASTERN)
    )
    after_holiday_before_open = calendar.latest_completed_session(
        datetime(2026, 9, 8, 8, tzinfo=EASTERN)
    )

    assert weekend.trading_date == date(2026, 9, 4)
    assert labor_day.trading_date == date(2026, 9, 4)
    assert after_holiday_before_open.trading_date == date(2026, 9, 4)


def test_latest_completed_session_respects_early_close() -> None:
    calendar = NyseTradingCalendar()

    session = calendar.latest_completed_session(
        datetime(2026, 11, 27, 13, 30, tzinfo=EASTERN)
    )

    assert session.trading_date == date(2026, 11, 27)
    assert session.closed_at.astimezone(EASTERN).hour == 13


def test_completed_month_dates_include_only_sessions_already_closed() -> None:
    calendar = NyseTradingCalendar()

    dates = calendar.completed_trading_dates_in_month(
        datetime(2026, 9, 6, 12, tzinfo=EASTERN), 2026, 9
    )

    assert dates == tuple(date(2026, 9, day) for day in (1, 2, 3, 4))
