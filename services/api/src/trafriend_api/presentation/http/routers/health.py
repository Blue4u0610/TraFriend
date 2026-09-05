from typing import Literal, cast

from fastapi import APIRouter, Depends

from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.presentation.http.dependencies import get_market_data_service
from trafriend_api.presentation.http.schemas import HealthResponse

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse)
def health(
    service: MarketDataService = Depends(get_market_data_service),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="trafriend-api",
        market_data_provider=cast(Literal["mock"], service.provider_code),
    )
