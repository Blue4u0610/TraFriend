from functools import lru_cache

from fastapi import Request

from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryDailyCloseAnchorRepository
from trafriend_api.presentation.http.schemas import ResponseMeta


@lru_cache(maxsize=1)
def get_market_data_service() -> MarketDataService:
    provider = MockMarketDataProvider()
    anchor_service = DailyCloseAnchorService(
        provider=provider,
        calendar=NyseTradingCalendar(),
        repository=InMemoryDailyCloseAnchorRepository(),
    )
    relationships = {
        relationship.id: relationship
        for instrument_id in ("ins_qqq_xnas", "ins_nvda_xnas")
        for relationship in provider.get_leveraged_relationships(instrument_id)
    }
    for relationship in relationships.values():
        anchor_service.capture(
            relationship_id=relationship.id,
            underlying_symbol=relationship.underlying.symbol,
            leveraged_product_symbol=relationship.leveraged_product.symbol,
        )
    return MarketDataService(provider=provider, anchor_service=anchor_service)


def response_meta(request: Request, include_cursor: bool = False) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id,
        next_cursor=None if include_cursor else None,
    )
