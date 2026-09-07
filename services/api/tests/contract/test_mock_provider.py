from datetime import date, datetime, timezone
from decimal import Decimal

from trafriend_api.application.ports.daily_close import DailyCloseMarketDataProvider
from trafriend_api.application.ports.market_data import MarketDataProvider
from trafriend_api.application.ports.overnight_market_data import OvernightMarketDataProvider
from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.domain.daily_close import DailyCloseAnchorStatus, DailyCloseQuality
from trafriend_api.domain.errors import AnchorUnavailableError
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryDailyCloseAnchorRepository

UTC = timezone.utc
NOW = datetime(2026, 9, 4, 21, tzinfo=UTC)


def test_mock_provider_conforms_to_market_data_port() -> None:
    provider = MockMarketDataProvider()

    assert isinstance(provider, MarketDataProvider)
    assert isinstance(provider, OvernightMarketDataProvider)
    assert isinstance(provider, DailyCloseMarketDataProvider)
    assert provider.provider_code == "mock"
    assert provider.capabilities.true_overnight
    assert provider.capabilities.batch_quotes

    search_results = provider.search_instruments("qqq", 10)
    assert [instrument.symbol for instrument in search_results] == [
        "QQQ",
        "QLD",
        "SQQQ",
        "TQQQ",
    ]

    relationships = provider.get_leveraged_relationships("ins_tqqq_xnas")
    assert {item.leveraged_product.symbol for item in relationships} == {
        "QLD",
        "TQQQ",
        "SQQQ",
    }
    assert {item.leverage_factor for item in relationships} == {
        Decimal("2"),
        Decimal("3"),
        Decimal("-3"),
    }
    sndk_relationship = provider.get_relationship("rel_sndk_snxx_2x")
    assert sndk_relationship.underlying.symbol == "SNDK"
    assert sndk_relationship.leveraged_product.symbol == "SNXX"
    assert sndk_relationship.leverage_factor == Decimal("2")

    bars = provider.get_daily_close_bars(
        ("QQQ", "TQQQ"), date(2026, 9, 4), date(2026, 9, 4)
    )
    assert [bar.close for bar in bars] == [Decimal("480.00"), Decimal("82.50")]
    assert all(bar.quality == DailyCloseQuality.REALTIME for bar in bars)
    assert all(bar.source == "mock" for bar in bars)

    history = provider.get_profit_ratio_history(
        "ins_nvda_xnas", date(2026, 9, 1), date(2026, 9, 4)
    )
    assert history.ratio_points
    assert all(Decimal("0") <= point.ratio <= Decimal("1") for point in history.ratio_points)
    assert tuple(point.trading_date for point in history.ratio_points) == tuple(
        sorted(point.trading_date for point in history.ratio_points)
    )


def test_named_mock_scenarios_are_deterministic() -> None:
    assert MockMarketDataProvider("inverse").get_relationship(
        "rel_qqq_sqqq_n3x"
    ).leverage_factor == Decimal("-3")
    stale = MockMarketDataProvider("stale", now=lambda: NOW).get_daily_close_bars(
        ("QQQ", "TQQQ"), date(2026, 9, 4), date(2026, 9, 4)
    )
    assert all(bar.quality == DailyCloseQuality.STALE for bar in stale)
    boundary = MockMarketDataProvider(
        "boundary", now=lambda: NOW
    ).get_daily_close_bars(
        ("QQQ", "TQQQ"), date(2026, 9, 4), date(2026, 9, 4)
    )
    assert all(bar.close == Decimal("0.01000000") for bar in boundary)

    for scenario in ("missing", "holiday"):
        bars = MockMarketDataProvider(
            scenario, now=lambda: NOW
        ).get_daily_close_bars(
            ("QQQ", "TQQQ"), date(2026, 9, 4), date(2026, 9, 4)
        )
        assert bars == ()

    partial = MockMarketDataProvider(
        "partial", now=lambda: NOW
    ).get_daily_close_bars(
        ("QQQ", "TQQQ"), date(2026, 9, 4), date(2026, 9, 4)
    )
    assert [bar.symbol for bar in partial] == ["QQQ"]


def test_incomplete_anchor_cannot_be_used_for_calculation() -> None:
    provider = MockMarketDataProvider("stale", now=lambda: NOW)
    anchor_service = DailyCloseAnchorService(
        provider=provider,
        calendar=NyseTradingCalendar(),
        repository=InMemoryDailyCloseAnchorRepository(),
        now=lambda: NOW,
    )
    anchor = anchor_service.capture(
        "rel_qqq_tqqq_3x", "QQQ", "TQQQ", Decimal("3")
    )
    service = MarketDataService(provider, anchor_service, provider)

    assert anchor.status == DailyCloseAnchorStatus.UNAVAILABLE

    try:
        service.calculate(
            relationship_id="rel_qqq_tqqq_3x",
            anchor_version_id=anchor.id,
            input_side="underlying",
            target_price=Decimal("500"),
        )
    except AnchorUnavailableError:
        pass
    else:
        raise AssertionError("incomplete anchor should not be eligible for calculation")
