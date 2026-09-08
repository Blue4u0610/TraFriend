from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel

from trafriend_api.application.services.profit_ratio import (
    ProfitRatioDailyHistory,
    ProfitRatioService,
)
from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioCalendarRangeError,
)
from trafriend_api.presentation.http.dependencies import response_meta
from trafriend_api.presentation.http.schemas import ResponseMeta

router = APIRouter(prefix="/api/v1/profit-ratio", tags=["profit-ratio"])


class ProfitRatioConstituentResponse(BaseModel):
    data: List[NasdaqConstituent]
    meta: ResponseMeta


class ProfitRatioDailyResponse(BaseModel):
    data: ProfitRatioDailyHistory
    meta: ResponseMeta


def get_profit_ratio_service(request: Request) -> ProfitRatioService:
    service: ProfitRatioService = request.app.state.profit_ratio_service
    return service


@router.get("/universe/search", response_model=ProfitRatioConstituentResponse)
def search(
    request: Request,
    q: str = Query("", max_length=64),
    limit: int = Query(25, ge=1, le=25),
    service: ProfitRatioService = Depends(get_profit_ratio_service),
) -> ProfitRatioConstituentResponse:
    return ProfitRatioConstituentResponse(
        data=list(service.search(q, limit)), meta=response_meta(request)
    )


@router.get("/symbols/{symbol}/daily", response_model=ProfitRatioDailyResponse)
def daily(
    request: Request,
    symbol: str = Path(..., pattern=r"^[A-Za-z0-9.-]{1,16}$"),
    start: date = Query(...),
    end: date = Query(...),
    service: ProfitRatioService = Depends(get_profit_ratio_service),
) -> ProfitRatioDailyResponse:
    if end < start or (end - start).days > 366:
        raise HTTPException(status_code=422, detail="use an ordered date range of at most 366 days")
    try:
        history = service.daily(symbol, start, end)
    except ProfitRatioCalendarRangeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROFIT_RATIO_CALENDAR_RANGE_UNSUPPORTED",
                "message": "requested dates are outside supported exchange-calendar coverage",
            },
        ) from exc
    return ProfitRatioDailyResponse(data=history, meta=response_meta(request))
