from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, cast

from fastapi import Request
from sqlalchemy import Engine

from trafriend_api.application.ports.daily_close import (
    DailyCloseAnchorRepository,
    DailyCloseMarketDataProvider,
)
from trafriend_api.application.ports.daily_price import DailyPriceRepository
from trafriend_api.application.ports.market_data import LeveragedRelationshipCatalog
from trafriend_api.application.ports.profit_ratio import ProfitRatioRepository
from trafriend_api.application.ports.ranking import MarketRankingRepository
from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.application.services.profit_ratio import ProfitRatioService
from trafriend_api.application.services.universe import UniverseService
from trafriend_api.domain.errors import ProviderAuthenticationError
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.catalog import (
    InMemoryLeveragedRelationshipCatalog,
    PostgreSQLLeveragedUniverseRepository,
)
from trafriend_api.infrastructure.market_data.alpaca import AlpacaMarketDataProvider
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.market_data.mock.daily_price import (
    build_mock_daily_price_repository,
)
from trafriend_api.infrastructure.market_data.mock.profit_ratio import (
    build_mock_profit_ratio_repository,
)
from trafriend_api.infrastructure.persistence import (
    InMemoryDailyCloseAnchorRepository,
    InMemoryMarketRankingRepository,
    PostgreSQLDailyCloseAnchorRepository,
    PostgreSQLMarketRankingRepository,
)
from trafriend_api.infrastructure.persistence.daily_price import PostgreSQLDailyPriceRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)
from trafriend_api.presentation.http.schemas import ResponseMeta
from trafriend_api.settings import Settings


@dataclass(frozen=True)
class ApplicationServices:
    market_data: MarketDataService
    universe: UniverseService
    profit_ratio: ProfitRatioService


def build_application_services(
    settings: Settings,
    database_engine: Optional[Engine] = None,
) -> ApplicationServices:
    mock_provider = MockMarketDataProvider()
    mock_relationships = {
        relationship.id: relationship
        for instrument in mock_provider.search_instruments("", limit=25)
        for relationship in mock_provider.get_leveraged_relationships(instrument.id)
    }
    if settings.database_url is None:
        profit_repository: ProfitRatioRepository = build_mock_profit_ratio_repository()
        price_repository: DailyPriceRepository = build_mock_daily_price_repository()
        repository: DailyCloseAnchorRepository = InMemoryDailyCloseAnchorRepository()
        catalog: LeveragedRelationshipCatalog = InMemoryLeveragedRelationshipCatalog(
            mock_relationships.values()
        )
        rankings: MarketRankingRepository = InMemoryMarketRankingRepository()
    else:
        engine = database_engine or create_database_engine(
            settings.database_url.get_secret_value()
        )
        profit_repository = PostgreSQLProfitRatioRepository(engine)
        price_repository = PostgreSQLDailyPriceRepository(engine)
        repository = PostgreSQLDailyCloseAnchorRepository(engine)
        catalog = PostgreSQLLeveragedUniverseRepository(engine)
        rankings = PostgreSQLMarketRankingRepository(engine)

    capture_provider = _daily_close_provider(settings, mock_provider)
    anchor_service = DailyCloseAnchorService(
        provider=capture_provider,
        calendar=NyseTradingCalendar(),
        repository=repository,
    )
    if settings.database_url is None:
        for relationship in mock_relationships.values():
            anchor_service.capture(
                relationship_id=relationship.id,
                underlying_symbol=relationship.underlying.symbol,
                leveraged_product_symbol=relationship.leveraged_product.symbol,
                signed_leverage=relationship.leverage_factor,
            )
    return ApplicationServices(
        profit_ratio=ProfitRatioService(
            profit_repository, ProfitRatioExchangeCalendar(), price_repository=price_repository
        ),
        market_data=MarketDataService(
            provider=mock_provider,
            anchor_service=anchor_service,
            relationship_catalog=catalog,
        ),
        universe=UniverseService(
            catalog=catalog,
            ranking_repository=rankings,
            anchor_service=anchor_service,
            capture_enabled=(
                settings.database_url is None
                or settings.daily_close_provider == "alpaca"
            ),
        ),
    )


def build_market_data_service(settings: Settings) -> MarketDataService:
    """Compatibility composition helper retained for existing callers."""
    return build_application_services(settings).market_data


def _daily_close_provider(
    settings: Settings,
    mock_provider: MockMarketDataProvider,
) -> DailyCloseMarketDataProvider:
    if settings.daily_close_provider == "mock":
        return mock_provider
    if settings.daily_close_provider != "alpaca":
        raise ValueError("TRAFRIEND_DAILY_CLOSE_PROVIDER must be mock or alpaca")
    if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
        raise ProviderAuthenticationError(
            "Alpaca credentials are required for the Alpaca daily-close provider"
        )
    return AlpacaMarketDataProvider(
        key_id=settings.alpaca_key_id.get_secret_value(),
        secret_key=settings.alpaca_secret_key.get_secret_value(),
        base_url=settings.alpaca_data_base_url,
        snapshot_feed=settings.alpaca_snapshot_feed,
        bars_feed=settings.alpaca_bars_feed,
        snapshot_quality=settings.alpaca_snapshot_quality,
        bars_quality=settings.alpaca_bars_quality,
        daily_bars_feed=settings.alpaca_daily_bars_feed,
        daily_bars_quality=settings.alpaca_daily_bars_quality,
    )


def get_market_data_service(request: Request) -> MarketDataService:
    return cast(MarketDataService, request.app.state.market_data_service)


def get_universe_service(request: Request) -> UniverseService:
    return cast(UniverseService, request.app.state.universe_service)


def response_meta(request: Request, include_cursor: bool = False) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id,
        next_cursor=None if include_cursor else None,
    )
