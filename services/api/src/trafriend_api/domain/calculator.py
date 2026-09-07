from __future__ import annotations

from decimal import Decimal

from trafriend_api.domain.daily_close import (
    DailyCloseAnchor,
    DailyCloseAnchorStatus,
    DailyCloseValueStatus,
)
from trafriend_api.domain.errors import (
    CalculationOutOfDomainError,
    FinancialInputError,
)
from trafriend_api.domain.models import CalculationResult, LeveragedRelationship


def _require_positive_finite(name: str, value: Decimal) -> None:
    if not value.is_finite() or value <= 0:
        raise FinancialInputError(f"{name} must be a finite value greater than zero")


def calculate_theoretical_target(
    relationship: LeveragedRelationship,
    anchor: DailyCloseAnchor,
    input_side: str,
    target_price: Decimal,
) -> CalculationResult:
    """Calculate a theoretical same-day target from one immutable close pair."""

    if anchor.relationship_id != relationship.id:
        raise FinancialInputError("Daily Close Anchor does not belong to the relationship")
    if anchor.status != DailyCloseAnchorStatus.COMPLETE:
        raise FinancialInputError("Daily Close Anchor must contain a complete pair")
    if (
        anchor.underlying.status != DailyCloseValueStatus.AVAILABLE
        or anchor.leveraged_product.status != DailyCloseValueStatus.AVAILABLE
        or anchor.underlying.close is None
        or anchor.leveraged_product.close is None
    ):
        raise FinancialInputError("Daily Close Anchor values are unavailable")
    if anchor.underlying.symbol != relationship.underlying.symbol:
        raise FinancialInputError("underlying anchor symbol does not match the relationship")
    if anchor.leveraged_product.symbol != relationship.leveraged_product.symbol:
        raise FinancialInputError(
            "leveraged-product anchor symbol does not match the relationship"
        )

    underlying_close = anchor.underlying.close
    leveraged_close = anchor.leveraged_product.close
    _require_positive_finite("underlying close", underlying_close)
    _require_positive_finite("leveraged-product close", leveraged_close)
    _require_positive_finite("target price", target_price)

    leverage_factor = relationship.leverage_factor
    if not leverage_factor.is_finite() or leverage_factor == 0:
        raise FinancialInputError("leverage factor must be finite and non-zero")
    if anchor.signed_leverage != leverage_factor:
        raise FinancialInputError(
            "Daily Close Anchor leverage does not match the relationship"
        )

    if input_side == "underlying":
        underlying_return = target_price / underlying_close - Decimal("1")
        leveraged_return = leverage_factor * underlying_return
        output_price = leveraged_close * (
            Decimal("1") + leveraged_return
        )
        output_side = "leveraged_product"
    elif input_side == "leveraged_product":
        leveraged_return = target_price / leveraged_close - Decimal("1")
        underlying_return = leveraged_return / leverage_factor
        output_price = underlying_close * (
            Decimal("1") + underlying_return
        )
        output_side = "underlying"
    else:
        raise FinancialInputError(
            "input side must be 'underlying' or 'leveraged_product'"
        )

    if not output_price.is_finite() or output_price <= 0:
        raise CalculationOutOfDomainError(
            "the target falls outside the positive-price domain of the single-day model"
        )

    return CalculationResult(
        input_side=input_side,
        input_target_price=target_price,
        output_side=output_side,
        theoretical_target_price=output_price,
        underlying_return=underlying_return,
        leveraged_return=leveraged_return,
    )
