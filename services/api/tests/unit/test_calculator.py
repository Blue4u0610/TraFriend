from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from trafriend_api.domain.calculator import calculate_theoretical_target
from trafriend_api.domain.daily_close import (
    DailyCloseAnchor,
    DailyCloseAnchorStatus,
    DailyCloseAnchorValue,
    DailyCloseQuality,
    DailyCloseValueStatus,
)
from trafriend_api.domain.errors import (
    CalculationOutOfDomainError,
    FinancialInputError,
)
from trafriend_api.domain.models import LeveragedRelationship
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider

UTC = timezone.utc
STAMP = datetime(2026, 9, 4, 20, 1, tzinfo=UTC)


def _anchor(
    relationship: LeveragedRelationship,
    underlying_close: str,
    leveraged_close: str,
) -> DailyCloseAnchor:
    def value(symbol: str, close: str) -> DailyCloseAnchorValue:
        return DailyCloseAnchorValue(
            symbol=symbol,
            close=Decimal(close),
            trading_date=date(2026, 9, 4),
            market_timestamp=datetime(2026, 9, 4, 4, tzinfo=UTC),
            observed_at=STAMP,
            source="test",
            source_feed="daily",
            currency="USD",
            quality=DailyCloseQuality.DELAYED,
            status=DailyCloseValueStatus.AVAILABLE,
            message="test anchor",
        )

    return DailyCloseAnchor(
        id="anchor_test_v1",
        relationship_id=relationship.id,
        trading_date=date(2026, 9, 4),
        status=DailyCloseAnchorStatus.COMPLETE,
        version=1,
        underlying=value(relationship.underlying.symbol, underlying_close),
        leveraged_product=value(
            relationship.leveraged_product.symbol, leveraged_close
        ),
        session_closed_at=datetime(2026, 9, 4, 20, tzinfo=UTC),
        captured_at=STAMP,
        provider="test",
        source_feed="daily",
        signed_leverage=relationship.leverage_factor,
        created_at=STAMP,
    )


@pytest.fixture()
def provider() -> MockMarketDataProvider:
    return MockMarketDataProvider()


@pytest.mark.parametrize(
    ("relationship_id", "underlying_close", "leveraged_close", "target", "expected"),
    [
        ("rel_nvda_nvdl_2x", "100", "20", "105", Decimal("22.0")),
        ("rel_qqq_tqqq_3x", "100", "10", "102", Decimal("10.60")),
        ("rel_qqq_sqqq_n3x", "100", "20", "98", Decimal("21.20")),
    ],
)
def test_forward_calculation_supports_plus_two_plus_three_and_minus_three(
    provider: MockMarketDataProvider,
    relationship_id: str,
    underlying_close: str,
    leveraged_close: str,
    target: str,
    expected: Decimal,
) -> None:
    relationship = provider.get_relationship(relationship_id)
    result = calculate_theoretical_target(
        relationship,
        _anchor(relationship, underlying_close, leveraged_close),
        "underlying",
        Decimal(target),
    )

    assert result.theoretical_target_price == expected
    assert result.formula_version == "leveraged-daily-close-linear/v2"


@pytest.mark.parametrize(
    ("relationship_id", "underlying_close", "leveraged_close", "target", "expected"),
    [
        ("rel_nvda_nvdl_2x", "100", "20", "22", Decimal("105.0")),
        ("rel_qqq_sqqq_n3x", "100", "20", "21.2", Decimal("98.00")),
    ],
)
def test_reverse_calculation_supports_plus_two_and_minus_three(
    provider: MockMarketDataProvider,
    relationship_id: str,
    underlying_close: str,
    leveraged_close: str,
    target: str,
    expected: Decimal,
) -> None:
    relationship = provider.get_relationship(relationship_id)
    result = calculate_theoretical_target(
        relationship,
        _anchor(relationship, underlying_close, leveraged_close),
        "leveraged_product",
        Decimal(target),
    )

    assert result.theoretical_target_price == expected


@pytest.mark.parametrize(
    "relationship_id",
    ["rel_qqq_tqqq_3x", "rel_qqq_sqqq_n3x", "rel_nvda_nvdl_2x"],
)
def test_forward_and_reverse_round_trip(
    provider: MockMarketDataProvider, relationship_id: str
) -> None:
    relationship = provider.get_relationship(relationship_id)
    anchor = _anchor(relationship, "123.456789", "19.87654321")
    underlying_target = Decimal("128.39506056")
    forward = calculate_theoretical_target(
        relationship, anchor, "underlying", underlying_target
    )
    reverse = calculate_theoretical_target(
        relationship,
        anchor,
        "leveraged_product",
        forward.theoretical_target_price,
    )

    assert reverse.theoretical_target_price == underlying_target


def test_zero_move_preserves_close_anchor(provider: MockMarketDataProvider) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    anchor = _anchor(relationship, "100", "10")
    result = calculate_theoretical_target(
        relationship, anchor, "underlying", Decimal("100")
    )

    assert result.underlying_return == Decimal("0")
    assert result.leveraged_return == Decimal("0")
    assert result.theoretical_target_price == Decimal("10")


def test_preserves_decimal_precision(provider: MockMarketDataProvider) -> None:
    relationship = provider.get_relationship("rel_nvda_nvdl_2x")
    anchor = _anchor(relationship, "7", "11")
    result = calculate_theoretical_target(
        relationship, anchor, "underlying", Decimal("8")
    )

    expected_return = Decimal("8") / Decimal("7") - Decimal("1")
    assert result.underlying_return == expected_return
    assert result.theoretical_target_price == Decimal("11") * (
        Decimal("1") + Decimal("2") * expected_return
    )


@pytest.mark.parametrize("target", [Decimal("0"), Decimal("-1"), Decimal("NaN")])
def test_rejects_invalid_target_prices(
    provider: MockMarketDataProvider, target: Decimal
) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    with pytest.raises(FinancialInputError):
        calculate_theoretical_target(
            relationship, _anchor(relationship, "100", "10"), "underlying", target
        )


def test_rejects_non_positive_theoretical_result(
    provider: MockMarketDataProvider,
) -> None:
    relationship = provider.get_relationship("rel_qqq_sqqq_n3x")
    with pytest.raises(CalculationOutOfDomainError):
        calculate_theoretical_target(
            relationship,
            _anchor(relationship, "100", "20"),
            "underlying",
            Decimal("150"),
        )


def test_rejects_anchor_from_another_relationship(
    provider: MockMarketDataProvider,
) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    other = provider.get_relationship("rel_nvda_nvdl_2x")
    with pytest.raises(FinancialInputError, match="does not belong"):
        calculate_theoretical_target(
            relationship, _anchor(other, "100", "20"), "underlying", Decimal("105")
        )


def test_rejects_zero_leverage(provider: MockMarketDataProvider) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    invalid = replace(relationship, leverage_factor=Decimal("0"))
    with pytest.raises(FinancialInputError):
        calculate_theoretical_target(
            invalid, _anchor(relationship, "100", "10"), "underlying", Decimal("105")
        )
