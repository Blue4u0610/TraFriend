from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Sequence

from trafriend_api.application.ports.ranking import (
    RankingMarketDataProvider,
    RankingSessionCalendar,
)
from trafriend_api.application.services.ranking import (
    MarketRankingService,
    is_eligible_operating_equity,
)
from trafriend_api.domain.universe import RankingAsset, RankingDailyBar, RankingType
from trafriend_api.infrastructure.catalog import InMemoryLeveragedRelationshipCatalog
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryMarketRankingRepository

UTC = timezone.utc
NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
DATES = tuple(date(2026, 9, day) for day in (1, 2, 3, 4))


class FakeCalendar(RankingSessionCalendar):
    def completed_trading_dates_in_month(
        self, timestamp: datetime, year: int, month: int
    ) -> Sequence[date]:
        assert timestamp == NOW
        assert (year, month) == (2026, 9)
        return DATES


class FakeRankingProvider(RankingMarketDataProvider):
    @property
    def provider_code(self) -> str:
        return "fake"

    @property
    def source_feed(self) -> str:
        return "sip"

    def list_active_us_equities(self) -> Sequence[RankingAsset]:
        return tuple(
            RankingAsset(
                symbol=f"C{index:03d}",
                name=f"Company {index:03d}",
                exchange="NASDAQ",
                status="active",
                tradable=True,
            )
            for index in range(105)
        )

    def get_daily_ranking_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[RankingDailyBar]:
        assert len(symbols) == 105
        assert (start, end) == (DATES[0], DATES[-1])
        bars = []
        for symbol in symbols:
            index = int(symbol[1:])
            dates = DATES[:-1] if symbol == "C104" else DATES
            for trading_date in dates:
                bars.append(
                    RankingDailyBar(
                        symbol=symbol,
                        trading_date=trading_date,
                        vwap=Decimal(1000 - index),
                        volume=Decimal("100"),
                        source="fake",
                        source_feed="sip",
                    )
                )
        return tuple(bars)


def _catalog() -> InMemoryLeveragedRelationshipCatalog:
    provider = MockMarketDataProvider(now=lambda: NOW)
    relationships = {
        relationship.id: relationship
        for instrument in provider.search_instruments("", 25)
        for relationship in provider.get_leveraged_relationships(instrument.id)
    }
    return InMemoryLeveragedRelationshipCatalog(relationships.values())


def test_ranking_build_aggregates_vwap_times_volume_and_replaces_idempotently() -> None:
    repository = InMemoryMarketRankingRepository(today=lambda: date(2026, 9, 6))
    service = MarketRankingService(
        provider=FakeRankingProvider(),
        calendar=FakeCalendar(),
        repository=repository,
        catalog=_catalog(),
        now=lambda: NOW,
    )

    first = service.build_september_2026()
    second = service.build_september_2026()
    dataset = repository.get_dataset("2026-09", RankingType.DOLLAR_TRADING_VOLUME)

    assert first.completed_trading_dates == DATES
    assert first.candidate_assets == 105
    assert first.complete_assets == 104
    assert first.incomplete_assets == 1
    assert first.persisted_rows == 100
    assert first.rows[0].symbol == "C000"
    assert first.rows[0].trading_metric == Decimal("400000")
    assert first.rows[0].sessions_observed == 4
    assert second.persisted_rows == 100
    assert len(dataset.rows) == 100
    assert dataset.population_status.value == "COMPLETE"


def test_security_policy_excludes_reliably_identified_non_operating_assets() -> None:
    included = RankingAsset("AAPL", "Apple Inc.", "NASDAQ", "active", True)
    etf = RankingAsset("SPY", "SPDR S&P 500 ETF Trust", "ARCA", "active", True)
    commodity_trust = RankingAsset(
        "GLD", "SPDR Gold Trust, SPDR Gold Shares", "ARCA", "active", True
    )
    warrant = RankingAsset("TEST.WS", "Test Corp Warrant", "NYSE", "active", True)
    preferred = RankingAsset("TESTP", "Test Corp Preferred Stock", "NYSE", "active", True)
    otc = RankingAsset("OTCX", "OTC Company", "OTC", "active", True)
    curated = RankingAsset("TQQQ", "Daily leveraged shares", "NASDAQ", "active", True)

    assert is_eligible_operating_equity(included, ())
    assert not is_eligible_operating_equity(etf, ())
    assert not is_eligible_operating_equity(commodity_trust, ())
    assert not is_eligible_operating_equity(warrant, ())
    assert not is_eligible_operating_equity(preferred, ())
    assert not is_eligible_operating_equity(otc, ())
    assert not is_eligible_operating_equity(curated, ("TQQQ",))
