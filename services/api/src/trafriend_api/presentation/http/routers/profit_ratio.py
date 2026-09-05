from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.domain.errors import ResourceNotFoundError
from trafriend_api.presentation.http.dependencies import (
    get_market_data_service,
    response_meta,
)
from trafriend_api.presentation.http.schemas import (
    InstrumentSchema,
    MethodologySchema,
    PricePointSchema,
    ProfitRatioHistoryData,
    ProfitRatioHistoryResponse,
    ProfitRatioLatestData,
    ProfitRatioLatestResponse,
    ProfitRatioPointSchema,
)

router = APIRouter(prefix="/api/v1/profit-ratio", tags=["profit-ratio"])


@router.get(
    "/instruments/{instrument_id}/latest", response_model=ProfitRatioLatestResponse
)
def get_latest(
    instrument_id: str,
    request: Request,
    service: MarketDataService = Depends(get_market_data_service),
) -> ProfitRatioLatestResponse:
    history = service.get_profit_ratio_history(instrument_id, date.min, date.max)
    if not history.ratio_points:
        raise ResourceNotFoundError("no Profit Ratio observations were found")
    latest = history.ratio_points[-1]
    return ProfitRatioLatestResponse(
        data=ProfitRatioLatestData(
            instrument=InstrumentSchema.model_validate(history.instrument),
            ratio=latest.ratio,
            observed_at=latest.timestamp,
            trading_date=latest.trading_date,
            freshness="current",
            methodology=MethodologySchema.model_validate(history.methodology),
            provider=history.provider,
        ),
        meta=response_meta(request),
    )


@router.get(
    "/instruments/{instrument_id}/history", response_model=ProfitRatioHistoryResponse
)
def get_history(
    instrument_id: str,
    request: Request,
    start: date = Query(...),
    end: date = Query(...),
    interval: Literal["1d"] = Query("1d"),
    include_price: bool = Query(True),
    service: MarketDataService = Depends(get_market_data_service),
) -> ProfitRatioHistoryResponse:
    if end < start:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="end must be on or after start")
    history = service.get_profit_ratio_history(instrument_id, start, end)
    return ProfitRatioHistoryResponse(
        data=ProfitRatioHistoryData(
            instrument_id=history.instrument.id,
            symbol=history.instrument.symbol,
            interval=interval,
            timezone="America/New_York",
            methodology=MethodologySchema.model_validate(history.methodology),
            profit_ratio_series=[
                ProfitRatioPointSchema.model_validate(point)
                for point in history.ratio_points
            ],
            price_series=(
                [PricePointSchema.model_validate(point) for point in history.price_points]
                if include_price
                else []
            ),
            gaps=[],
            as_of=history.as_of,
            provider=history.provider,
        ),
        meta=response_meta(request),
    )

