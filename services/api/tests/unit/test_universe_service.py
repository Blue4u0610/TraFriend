from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

import pytest

from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.application.services.universe import UniverseService
from trafriend_api.domain.daily_close import DailyCloseBar
from trafriend_api.domain.errors import ResourceNotFoundError
from trafriend_api.domain.universe import (
    MarketRanking,
    RankingPeriodStatus,
    RankingType,
)
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.catalog import InMemoryLeveragedRelationshipCatalog
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import (
    InMemoryDailyCloseAnchorRepository,
    InMemoryMarketRankingRepository,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 4, 21, tzinfo=UTC)


def _catalog(provider: MockMarketDataProvider) -> InMemoryLeveragedRelationshipCatalog:
    relationships = {
        relationship.id: relationship
        for instrument in provider.search_instruments("", 25)
        for relationship in provider.get_leveraged_relationships(instrument.id)
    }
    return InMemoryLeveragedRelationshipCatalog(relationships.values())


def _service(
    provider: Optional[MockMarketDataProvider] = None,
    rankings: Optional[InMemoryMarketRankingRepository] = None,
) -> UniverseService:
    selected_provider = provider or MockMarketDataProvider(now=lambda: NOW)
    return UniverseService(
        catalog=_catalog(selected_provider),
        ranking_repository=rankings or InMemoryMarketRankingRepository(),
        anchor_service=DailyCloseAnchorService(
            provider=selected_provider,
            calendar=NyseTradingCalendar(),
            repository=InMemoryDailyCloseAnchorRepository(),
            now=lambda: NOW,
        ),
    )


def test_metadata_search_is_local_and_supports_non_popular_symbols() -> None:
    provider = MockMarketDataProvider(now=lambda: NOW)
    service = _service(provider)

    assert service.search("sandisk")[0].symbol == "SNDK"
    assert service.search("TSLL")[0].symbol == "TSLL"
    assert provider.daily_close_request_log == []


def test_metadata_search_scopes_underlyings_and_products() -> None:
    provider = MockMarketDataProvider(now=lambda: NOW)
    service = _service(provider)

    underlyings = service.search_underlyings("QQ", 10)
    products = service.search_leveraged_products("QQ", 10)

    assert [item.symbol for item in underlyings] == ["QQQ"]
    assert {item.symbol for item in products} == {"QLD", "TQQQ", "SQQQ"}
    assert all(item.instrument_type != "leveraged_etf" for item in underlyings)
    assert all(item.instrument_type == "leveraged_etf" for item in products)
    assert provider.daily_close_request_log == []


def test_on_demand_capture_then_cache_hit_avoids_provider() -> None:
    provider = MockMarketDataProvider(now=lambda: NOW)
    service = _service(provider)

    first = service.resolve("QQQ", capture_missing=True)
    first_calls = len(provider.daily_close_request_log)
    second = service.resolve("QQQ", capture_missing=True)

    assert first_calls == 3
    assert {row.anchor_source for row in first.rows} == {"ON_DEMAND"}
    assert {row.anchor_source for row in second.rows} == {"CACHE"}
    assert len(provider.daily_close_request_log) == first_calls


def test_disabled_on_demand_capture_never_calls_provider() -> None:
    provider = MockMarketDataProvider(now=lambda: NOW)
    service = UniverseService(
        catalog=_catalog(provider),
        ranking_repository=InMemoryMarketRankingRepository(),
        anchor_service=DailyCloseAnchorService(
            provider=provider,
            calendar=NyseTradingCalendar(),
            repository=InMemoryDailyCloseAnchorRepository(),
            now=lambda: NOW,
        ),
        capture_enabled=False,
    )

    workspace = service.resolve("QQQ", capture_missing=True)

    assert {row.status for row in workspace.rows} == {"UNAVAILABLE"}
    assert {row.anchor_source for row in workspace.rows} == {"NONE"}
    assert provider.daily_close_request_log == []


def test_one_underlying_target_calculates_long_and_inverse_products() -> None:
    service = _service()
    service.resolve("QQQ", capture_missing=True)

    calculation = service.calculate_all("QQQ", Decimal("504"))
    results = {
        row.relationship.leveraged_product.symbol: row.result
        for row in calculation.rows
    }

    assert results["QLD"] is not None
    assert results["TQQQ"] is not None
    assert results["SQQQ"] is not None
    assert results["QLD"].theoretical_target_price == Decimal("132")
    assert results["TQQQ"].theoretical_target_price == Decimal("94.875")
    assert results["SQQQ"].theoretical_target_price == Decimal("26.52")


class MissingQldProvider(MockMarketDataProvider):
    def get_daily_close_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[DailyCloseBar]:
        bars = super().get_daily_close_bars(symbols, start, end)
        return tuple(bar for bar in bars if bar.symbol != "QLD")


def test_daily_job_is_idempotent_and_isolates_one_missing_product() -> None:
    provider = MissingQldProvider(now=lambda: NOW)
    service = _service(provider)

    first = service.capture_symbols(("QQQ",))
    second = service.capture_symbols(("QQQ",))

    assert first.status == "PARTIAL"
    assert first.inserted == 2
    assert first.unavailable == 1
    assert second.existing == 2
    assert second.unavailable == 1
    assert set(first.leveraged_product_symbols) == {"QLD", "TQQQ", "SQQQ"}


def test_missing_product_anchor_yields_unavailable_row_only() -> None:
    service = _service(MissingQldProvider(now=lambda: NOW))
    service.capture_symbols(("QQQ",))

    calculation = service.calculate_all("QQQ", Decimal("504"))
    states = {
        row.relationship.leveraged_product.symbol: row.status
        for row in calculation.rows
    }

    assert states == {"QLD": "UNAVAILABLE", "TQQQ": "AVAILABLE", "SQQQ": "AVAILABLE"}


def test_popular_dataset_separates_period_and_population_semantics() -> None:
    row = MarketRanking(
        ranking_period="2026-09",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 4),
        period_status=RankingPeriodStatus.SEPTEMBER_TO_DATE,
        ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
        rank=1,
        symbol="QQQ",
        trading_metric=Decimal("123456789.12"),
        calculated_at=NOW,
        source="verified-test-fixture",
    )
    rankings = InMemoryMarketRankingRepository((row,), today=lambda: date(2026, 9, 6))
    service = _service(rankings=rankings)

    dataset = service.popular()

    assert dataset.period_status == RankingPeriodStatus.SEPTEMBER_TO_DATE
    assert dataset.population_status.value == "PARTIAL"
    assert dataset.rows == (row,)


def test_empty_september_dataset_becomes_final_only_after_month_end() -> None:
    september = _service(
        rankings=InMemoryMarketRankingRepository(
            today=lambda: date(2026, 9, 30)
        )
    ).popular()
    finalized = _service(
        rankings=InMemoryMarketRankingRepository(
            today=lambda: date(2026, 10, 1)
        )
    ).popular()

    assert september.period_status == RankingPeriodStatus.SEPTEMBER_TO_DATE
    assert finalized.period_status == RankingPeriodStatus.FINAL
    assert september.population_status.value == "NOT_POPULATED"
    assert finalized.population_status.value == "NOT_POPULATED"


def test_empty_current_non_september_dataset_is_month_to_date() -> None:
    dataset = _service(
        rankings=InMemoryMarketRankingRepository(
            today=lambda: date(2026, 10, 15)
        )
    ).popular(ranking_period="2026-10")

    assert dataset.period_status == RankingPeriodStatus.MONTH_TO_DATE
    assert dataset.population_status.value == "NOT_POPULATED"


def test_popular_capture_expands_ranked_underlying_to_every_product() -> None:
    provider = MockMarketDataProvider(now=lambda: NOW)
    row = MarketRanking(
        ranking_period="2026-09",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 4),
        period_status=RankingPeriodStatus.SEPTEMBER_TO_DATE,
        ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
        rank=1,
        symbol="QQQ",
        trading_metric=Decimal("123456789.12"),
        calculated_at=NOW,
        source="verified-test-fixture",
    )
    service = _service(
        provider=provider,
        rankings=InMemoryMarketRankingRepository((row,)),
    )

    report = service.capture_popular()

    assert report.status == "VALID"
    assert report.underlying_symbols == ("QQQ",)
    assert set(report.leveraged_product_symbols) == {"QLD", "TQQQ", "SQQQ"}
    assert report.inserted == 3


def test_unsupported_symbol_is_explicit() -> None:
    with pytest.raises(ResourceNotFoundError):
        _service().resolve("AAPL", capture_missing=False)
