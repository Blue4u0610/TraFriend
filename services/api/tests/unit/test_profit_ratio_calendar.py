from datetime import date, datetime, timezone

import pytest

from trafriend_api.domain.profit_ratio_daily import ProfitRatioCalendarRangeError
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar

UTC = timezone.utc


@pytest.fixture(scope="module")
def calendar() -> ProfitRatioExchangeCalendar:
    return ProfitRatioExchangeCalendar()


@pytest.mark.parametrize("trading_date", [
    date(2026, 9, 5), date(2026, 9, 6), date(2026, 9, 7),
    date(2026, 7, 3), date(2026, 11, 26),
])
def test_profit_ratio_calendar_rejects_weekends_and_exchange_holidays(
    calendar: ProfitRatioExchangeCalendar, trading_date: date
) -> None:
    with pytest.raises(ValueError, match="not a US equity trading session"):
        calendar.session(trading_date)


def test_profit_ratio_calendar_previous_session_skips_labor_day_weekend(
    calendar: ProfitRatioExchangeCalendar,
) -> None:
    session = calendar.session(date(2026, 9, 8))
    assert session.previous_trading_date == date(2026, 9, 4)
    assert session.opened_at == datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    assert session.closed_at == datetime(2026, 9, 8, 20, tzinfo=UTC)


def test_profit_ratio_calendar_uses_actual_early_close(
    calendar: ProfitRatioExchangeCalendar,
) -> None:
    session = calendar.session(date(2026, 11, 27))
    assert session.previous_trading_date == date(2026, 11, 25)
    assert session.opened_at == datetime(2026, 11, 27, 14, 30, tzinfo=UTC)
    assert session.closed_at == datetime(2026, 11, 27, 18, tzinfo=UTC)


@pytest.mark.parametrize(("trading_date", "open_hour", "close_hour"), [
    (date(2026, 3, 6), 14, 21),
    (date(2026, 3, 9), 13, 20),
    (date(2026, 10, 30), 13, 20),
    (date(2026, 11, 2), 14, 21),
])
def test_profit_ratio_calendar_keeps_local_boundary_across_dst(
    calendar: ProfitRatioExchangeCalendar, trading_date: date, open_hour: int, close_hour: int
) -> None:
    session = calendar.session(trading_date)
    assert session.opened_at == datetime(
        trading_date.year, trading_date.month, trading_date.day, open_hour, 30, tzinfo=UTC
    )
    assert session.closed_at == datetime(
        trading_date.year, trading_date.month, trading_date.day, close_hour, tzinfo=UTC
    )


def test_profit_ratio_calendar_range_preserves_only_real_sessions(
    calendar: ProfitRatioExchangeCalendar,
) -> None:
    assert [session.trading_date for session in calendar.sessions(
        date(2026, 9, 4), date(2026, 9, 9)
    )] == [date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9)]
    assert calendar.sessions(date(2026, 9, 5), date(2026, 9, 7)) == ()


def test_profit_ratio_calendar_rejects_reversed_range(
    calendar: ProfitRatioExchangeCalendar,
) -> None:
    with pytest.raises(ValueError, match="end must be on or after start"):
        calendar.sessions(date(2026, 9, 9), date(2026, 9, 4))


@pytest.mark.parametrize("requested", [date(1900, 1, 1), date(9999, 1, 1)])
def test_profit_ratio_calendar_rejects_unsupported_dates_with_typed_error(
    calendar: ProfitRatioExchangeCalendar, requested: date,
) -> None:
    with pytest.raises(ProfitRatioCalendarRangeError):
        calendar.session(requested)
    with pytest.raises(ProfitRatioCalendarRangeError):
        calendar.sessions(requested, requested)
