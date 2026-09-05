from datetime import datetime, timezone
from typing import Literal, cast

from fastapi import APIRouter, Depends, Request

from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.presentation.http.dependencies import (
    get_market_data_service,
    response_meta,
)
from trafriend_api.presentation.http.schemas import (
    CalculationData,
    CalculationInputSchema,
    CalculationOutputSchema,
    CalculationReferenceSchema,
    CalculationRequest,
    CalculationResponse,
    DailyReferenceResponse,
    DailyReferenceSetSchema,
    WarningSchema,
)

router = APIRouter(prefix="/api/v1/leveraged-etf", tags=["leveraged-etf"])


@router.get(
    "/relationships/{relationship_id}/reference",
    response_model=DailyReferenceResponse,
)
def get_reference(
    relationship_id: str,
    request: Request,
    service: MarketDataService = Depends(get_market_data_service),
) -> DailyReferenceResponse:
    reference = service.get_reference(relationship_id)
    return DailyReferenceResponse(
        data=DailyReferenceSetSchema.model_validate(reference),
        meta=response_meta(request),
    )


@router.post("/calculations", response_model=CalculationResponse)
def calculate(
    payload: CalculationRequest,
    request: Request,
    service: MarketDataService = Depends(get_market_data_service),
) -> CalculationResponse:
    relationship = service.get_relationship(payload.relationship_id)
    reference = service.get_reference(payload.relationship_id)
    result = service.calculate(
        relationship_id=payload.relationship_id,
        reference_version_id=payload.reference_version_id,
        input_side=payload.input_side,
        target_price=payload.target_price,
    )

    if result.input_side == "underlying":
        input_instrument = relationship.underlying
        output_instrument = relationship.leveraged_product
    else:
        input_instrument = relationship.leveraged_product
        output_instrument = relationship.underlying

    return CalculationResponse(
        data=CalculationData(
            formula_version=result.formula_version,
            relationship_id=relationship.id,
            leverage_factor=relationship.leverage_factor,
            objective_period=relationship.objective_period,
            input=CalculationInputSchema(
                side=cast(
                    Literal["underlying", "leveraged_product"], result.input_side
                ),
                instrument_id=input_instrument.id,
                symbol=input_instrument.symbol,
                target_price=result.input_target_price,
            ),
            output=CalculationOutputSchema(
                side=cast(
                    Literal["underlying", "leveraged_product"], result.output_side
                ),
                instrument_id=output_instrument.id,
                symbol=output_instrument.symbol,
                theoretical_target_price=result.theoretical_target_price,
            ),
            underlying_return=result.underlying_return,
            leveraged_return=result.leveraged_return,
            reference=CalculationReferenceSchema(
                id=reference.id,
                trading_date=reference.trading_date,
                session=reference.session,
                underlying_price=reference.underlying.price,
                leveraged_product_price=reference.leveraged_product.price,
                underlying_quoted_at=reference.underlying.quoted_at,
                leveraged_product_quoted_at=reference.leveraged_product.quoted_at,
                provider=reference.provider,
            ),
            calculated_at=datetime.now(timezone.utc),
            warnings=[
                WarningSchema(
                    code="THEORETICAL_SINGLE_DAY_ONLY",
                    message=(
                        "This estimate uses a single-day linear leverage relationship "
                        "and is not a multi-day price forecast."
                    ),
                )
            ],
        ),
        meta=response_meta(request),
    )
