from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trafriend_api.domain.overnight import (
    DataQuality,
    HistoricalOvernightBar,
    HistoricalOvernightQuote,
)
from trafriend_api.scripts.diagnose_overnight_history import (
    NO_OVERNIGHT_TRADE_DATA,
    OVERNIGHT_WITHOUT_OPENING_TRADE,
    VALID_OPENING_WINDOW_DATA,
    _classify_bars,
    _select_nearest_quote,
)

UTC = timezone.utc
SESSION_START = datetime(2026, 9, 4, 0, 0, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def _bar(starts_at: datetime) -> HistoricalOvernightBar:
    return HistoricalOvernightBar(
        symbol="SNXX",
        open_price=Decimal("20.00"),
        high_price=Decimal("20.10"),
        low_price=Decimal("19.90"),
        close_price=Decimal("20.05"),
        volume=Decimal("10"),
        starts_at=starts_at,
        observed_at=OBSERVED_AT,
        source="alpaca",
        source_feed="boats",
        quality=DataQuality.DELAYED,
    )


def _quote(timestamp: datetime) -> HistoricalOvernightQuote:
    return HistoricalOvernightQuote(
        symbol="SNXX",
        bid_price=Decimal("20.00"),
        ask_price=Decimal("20.10"),
        market_timestamp=timestamp,
        observed_at=OBSERVED_AT,
        source="alpaca",
        source_feed="boats",
        quality=DataQuality.DELAYED,
    )


def test_classifies_full_session_bar_outcomes() -> None:
    assert _classify_bars((), SESSION_START) == NO_OVERNIGHT_TRADE_DATA
    assert (
        _classify_bars((_bar(SESSION_START + timedelta(minutes=2)),), SESSION_START)
        == VALID_OPENING_WINDOW_DATA
    )
    assert (
        _classify_bars((_bar(SESSION_START + timedelta(minutes=15)),), SESSION_START)
        == OVERNIGHT_WITHOUT_OPENING_TRADE
    )


def test_selects_nearest_quote_and_uses_earlier_timestamp_for_a_tie() -> None:
    target = SESSION_START + timedelta(minutes=5)
    earlier = _quote(target - timedelta(milliseconds=100))
    later = _quote(target + timedelta(milliseconds=100))

    assert _select_nearest_quote((later, earlier), target) == earlier
    assert earlier.midpoint == Decimal("20.05")
