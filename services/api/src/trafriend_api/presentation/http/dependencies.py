from functools import lru_cache

from fastapi import Request

from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.presentation.http.schemas import ResponseMeta


@lru_cache(maxsize=1)
def get_market_data_service() -> MarketDataService:
    return MarketDataService(provider=MockMarketDataProvider())


def response_meta(request: Request, include_cursor: bool = False) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id,
        next_cursor=None if include_cursor else None,
    )

