from datetime import date
from decimal import Decimal

from trafriend_api.application.ports.market_data import MarketDataProvider
from trafriend_api.application.ports.overnight_market_data import OvernightMarketDataProvider
from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.domain.errors import ReferenceUnavailableError, ResourceNotFoundError
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider


def test_mock_provider_conforms_to_market_data_port() -> None:
    provider = MockMarketDataProvider()

    assert isinstance(provider, MarketDataProvider)
    assert isinstance(provider, OvernightMarketDataProvider)
    assert provider.provider_code == "mock"
    assert provider.capabilities.true_overnight
    assert provider.capabilities.batch_quotes

    search_results = provider.search_instruments("qqq", 10)
    assert [instrument.symbol for instrument in search_results] == ["QQQ", "SQQQ", "TQQQ"]

    relationships = provider.get_leveraged_relationships("ins_tqqq_xnas")
    assert {item.leveraged_product.symbol for item in relationships} == {"TQQQ", "SQQQ"}
    assert {item.leverage_factor for item in relationships} == {
        Decimal("3"),
        Decimal("-3"),
    }

    reference = provider.get_reference("rel_qqq_tqqq_3x")
    assert reference.underlying.price > 0
    assert reference.leveraged_product.price > 0
    assert reference.underlying.quoted_at.tzinfo is not None
    assert reference.leveraged_product.quoted_at.tzinfo is not None
    assert reference.provider == "mock"

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
    assert (
        MockMarketDataProvider("stale")
        .get_reference("rel_qqq_tqqq_3x")
        .freshness
        == "stale"
    )
    assert (
        MockMarketDataProvider("boundary")
        .get_reference("rel_qqq_tqqq_3x")
        .underlying.price
        == Decimal("0.01000000")
    )

    for scenario in ("missing", "holiday"):
        provider = MockMarketDataProvider(scenario)
        try:
            provider.get_reference("rel_qqq_tqqq_3x")
        except ResourceNotFoundError:
            pass
        else:
            raise AssertionError(f"{scenario} scenario should not publish references")

    partial = MockMarketDataProvider("partial")
    assert partial.get_reference("rel_qqq_tqqq_3x")
    try:
        partial.get_reference("rel_nvda_nvdl_2x")
    except ResourceNotFoundError:
        pass
    else:
        raise AssertionError("partial scenario should omit the NVDA reference")


def test_stale_reference_cannot_be_used_for_calculation() -> None:
    service = MarketDataService(MockMarketDataProvider("stale"))
    reference = service.get_reference("rel_qqq_tqqq_3x")

    try:
        service.calculate(
            relationship_id="rel_qqq_tqqq_3x",
            reference_version_id=reference.id,
            input_side="underlying",
            target_price=Decimal("500"),
        )
    except ReferenceUnavailableError:
        pass
    else:
        raise AssertionError("stale reference should not be eligible for calculation")
