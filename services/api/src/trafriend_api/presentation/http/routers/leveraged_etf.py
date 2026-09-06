from datetime import datetime, timezone
from typing import Literal, cast

from fastapi import APIRouter, Depends, Request

from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.presentation.http.dependencies import (
    get_market_data_service,
    response_meta,
)
from trafriend_api.presentation.http.schemas import (
    CalculationAnchorSchema,
    CalculationData,
    CalculationInputSchema,
    CalculationOutputSchema,
    CalculationRequest,
    CalculationResponse,
    DailyCloseAnchorResponse,
    DailyCloseAnchorSchema,
    WarningSchema,
)

router = APIRouter(prefix="/api/v1/leveraged-etf", tags=["leveraged-etf"])


@router.get(
    "/relationships/{relationship_id}/anchor",
    response_model=DailyCloseAnchorResponse,
)
def get_anchor(
    relationship_id: str,
    request: Request,
    service: MarketDataService = Depends(get_market_data_service),
) -> DailyCloseAnchorResponse:
    anchor = service.get_anchor(relationship_id)
    return DailyCloseAnchorResponse(
        data=DailyCloseAnchorSchema.model_validate(anchor),
        meta=response_meta(request),
    )


@router.post("/calculations", response_model=CalculationResponse)
def calculate(
    payload: CalculationRequest,
    request: Request,
    service: MarketDataService = Depends(get_market_data_service),
) -> CalculationResponse:
    relationship = service.get_relationship(payload.relationship_id)
    anchor = service.get_anchor(payload.relationship_id)
    result = service.calculate(
        relationship_id=payload.relationship_id,
        anchor_version_id=payload.anchor_version_id,
        input_side=payload.input_side,
        target_price=payload.target_price,
    )
    assert anchor.underlying.close is not None
    assert anchor.leveraged_product.close is not None
    assert anchor.underlying.market_timestamp is not None
    assert anchor.leveraged_product.market_timestamp is not None

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
            anchor=CalculationAnchorSchema(
                id=anchor.id,
                anchor_type="DAILY_CLOSE_ANCHOR",
                trading_date=anchor.trading_date,
                underlying_close=anchor.underlying.close,
                leveraged_product_close=anchor.leveraged_product.close,
                underlying_market_timestamp=anchor.underlying.market_timestamp,
                leveraged_product_market_timestamp=(
                    anchor.leveraged_product.market_timestamp
                ),
                provider=anchor.provider,
                source_feed=anchor.source_feed,
            ),
            calculated_at=datetime.now(timezone.utc),
            warnings=[
                WarningSchema(
                    code="THEORETICAL_SINGLE_DAY_ONLY",
                    message=(
                        "This estimate uses a single-day linear leverage relationship "
                        "anchored to the latest completed regular-session closes. "
                        "Daily-reset compounding means it is not a multi-day forecast."
                    ),
                ),
                WarningSchema(
                    code="ACTUAL_MARKET_PRICE_MAY_DIFFER",
                    message=(
                        "Actual ETF prices may differ because of bid/ask spreads, "
                        "premium or discount to NAV, tracking error, financing and "
                        "fees, liquidity, and market conditions."
                    ),
                ),
            ],
        ),
        meta=response_meta(request),
    )
