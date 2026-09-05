from dataclasses import replace
from decimal import Decimal

import pytest

from trafriend_api.domain.calculator import calculate_theoretical_target
from trafriend_api.domain.errors import (
    CalculationOutOfDomainError,
    FinancialInputError,
)
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider


@pytest.fixture()
def provider() -> MockMarketDataProvider:
    return MockMarketDataProvider()


@pytest.mark.parametrize(
    ("relationship_id", "target", "expected"),
    [
        ("rel_qqq_tqqq_3x", Decimal("528"), Decimal("107.250")),
        ("rel_qqq_sqqq_n3x", Decimal("528"), Decimal("21.840")),
        ("rel_nvda_nvdl_2x", Decimal("187"), Decimal("96.000")),
    ],
)
def test_forward_calculation_supports_long_and_inverse_leverage(
    provider: MockMarketDataProvider,
    relationship_id: str,
    target: Decimal,
    expected: Decimal,
) -> None:
    relationship = provider.get_relationship(relationship_id)
    reference = provider.get_reference(relationship_id)

    result = calculate_theoretical_target(
        relationship=relationship,
        reference=reference,
        input_side="underlying",
        target_price=target,
    )

    assert result.theoretical_target_price == expected
    assert result.formula_version == "leveraged-daily-linear/v1"


@pytest.mark.parametrize(
    ("leverage_factor", "expected"),
    [
        (Decimal("2"), Decimal("99.000")),
        (Decimal("3"), Decimal("107.250")),
        (Decimal("-1"), Decimal("74.250")),
        (Decimal("-2"), Decimal("66.000")),
        (Decimal("-3"), Decimal("57.750")),
    ],
)
def test_all_initial_leverage_factors(
    provider: MockMarketDataProvider,
    leverage_factor: Decimal,
    expected: Decimal,
) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    relationship = replace(relationship, leverage_factor=leverage_factor)
    reference = provider.get_reference(relationship.id)

    result = calculate_theoretical_target(
        relationship,
        reference,
        "underlying",
        Decimal("528"),
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
    reference = provider.get_reference(relationship_id)
    underlying_target = reference.underlying.price * Decimal("1.08")

    forward = calculate_theoretical_target(
        relationship,
        reference,
        "underlying",
        underlying_target,
    )
    reverse = calculate_theoretical_target(
        relationship,
        reference,
        "leveraged_product",
        forward.theoretical_target_price,
    )

    assert reverse.theoretical_target_price == underlying_target
    assert reverse.underlying_return == Decimal("0.08")


def test_zero_move_preserves_reference_price(
    provider: MockMarketDataProvider,
) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    reference = provider.get_reference(relationship.id)

    result = calculate_theoretical_target(
        relationship,
        reference,
        "underlying",
        reference.underlying.price,
    )

    assert result.underlying_return == Decimal("0")
    assert result.leveraged_return == Decimal("0")
    assert result.theoretical_target_price == reference.leveraged_product.price


@pytest.mark.parametrize("target", [Decimal("0"), Decimal("-1"), Decimal("NaN")])
def test_rejects_invalid_target_prices(
    provider: MockMarketDataProvider, target: Decimal
) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    reference = provider.get_reference(relationship.id)

    with pytest.raises(FinancialInputError):
        calculate_theoretical_target(
            relationship, reference, "underlying", target
        )


def test_rejects_non_positive_theoretical_result(
    provider: MockMarketDataProvider,
) -> None:
    relationship = provider.get_relationship("rel_qqq_sqqq_n3x")
    reference = provider.get_reference(relationship.id)

    with pytest.raises(CalculationOutOfDomainError):
        calculate_theoretical_target(
            relationship,
            reference,
            "underlying",
            Decimal("650"),
        )


def test_rejects_reference_from_another_relationship(
    provider: MockMarketDataProvider,
) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    other_reference = provider.get_reference("rel_nvda_nvdl_2x")

    with pytest.raises(FinancialInputError):
        calculate_theoretical_target(
            relationship,
            other_reference,
            "underlying",
            Decimal("500"),
        )


def test_rejects_zero_leverage(provider: MockMarketDataProvider) -> None:
    relationship = provider.get_relationship("rel_qqq_tqqq_3x")
    invalid_relationship = replace(relationship, leverage_factor=Decimal("0"))
    reference = provider.get_reference(relationship.id)

    with pytest.raises(FinancialInputError):
        calculate_theoretical_target(
            invalid_relationship,
            reference,
            "underlying",
            Decimal("500"),
        )
