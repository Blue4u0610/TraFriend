from __future__ import annotations

from decimal import Decimal

from trafriend_api.domain.errors import (
    CalculationOutOfDomainError,
    FinancialInputError,
)
from trafriend_api.domain.models import CalculationResult, DailyReferenceSet, LeveragedRelationship


def _require_positive_finite(name: str, value: Decimal) -> None:
    if not value.is_finite() or value <= 0:
        raise FinancialInputError(f"{name} must be a finite value greater than zero")


def calculate_theoretical_target(
    relationship: LeveragedRelationship,
    reference: DailyReferenceSet,
    input_side: str,
    target_price: Decimal,
) -> CalculationResult:
    """Calculate a theoretical same-day target from one immutable reference pair."""

    if reference.relationship_id != relationship.id:
        raise FinancialInputError("reference set does not belong to the relationship")

    _require_positive_finite("underlying reference price", reference.underlying.price)
    _require_positive_finite("leveraged reference price", reference.leveraged_product.price)
    _require_positive_finite("target price", target_price)

    leverage_factor = relationship.leverage_factor
    if not leverage_factor.is_finite() or leverage_factor == 0:
        raise FinancialInputError("leverage factor must be finite and non-zero")

    if input_side == "underlying":
        underlying_return = target_price / reference.underlying.price - Decimal("1")
        leveraged_return = leverage_factor * underlying_return
        output_price = reference.leveraged_product.price * (
            Decimal("1") + leveraged_return
        )
        output_side = "leveraged_product"
    elif input_side == "leveraged_product":
        leveraged_return = target_price / reference.leveraged_product.price - Decimal("1")
        underlying_return = leveraged_return / leverage_factor
        output_price = reference.underlying.price * (
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

