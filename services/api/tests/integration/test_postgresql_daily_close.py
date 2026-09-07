from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterator, Sequence
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from trafriend_api.application.ports.daily_close import (
    AnchorPersistenceOutcome,
    DailyCloseMarketDataProvider,
)
from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.domain.daily_close import (
    DailyCloseAnchor,
    DailyCloseAnchorStatus,
    DailyCloseAnchorValue,
    DailyCloseBar,
    DailyCloseQuality,
    DailyCloseValueStatus,
)
from trafriend_api.domain.errors import AnchorConflictError
from trafriend_api.domain.models import LeveragedRelationship
from trafriend_api.domain.universe import (
    MarketRanking,
    RankingPeriodStatus,
    RankingType,
)
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.catalog import (
    InMemoryLeveragedRelationshipCatalog,
    PostgreSQLLeveragedUniverseRepository,
)
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import (
    PostgreSQLDailyCloseAnchorRepository,
    PostgreSQLMarketRankingRepository,
)

UTC = timezone.utc
STAMP = datetime(2026, 9, 4, 21, tzinfo=UTC)


@dataclass(frozen=True)
class PostgreSQLTestContext:
    database_url: str
    schema: str
    engine: Engine

    def new_engine(self) -> Engine:
        return create_engine(
            self.database_url,
            connect_args={"options": f"-csearch_path={self.schema}"},
        )


@pytest.fixture(scope="module")
def postgresql_context() -> Iterator[PostgreSQLTestContext]:
    database_url = os.getenv("TRAFRIEND_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TRAFRIEND_TEST_DATABASE_URL is not configured")
    schema = f"test_daily_close_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

    schema_engine = create_engine(
        database_url,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    config = Config("alembic.ini")
    with schema_engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    assert {
        "daily_close_anchors",
        "underlyings",
        "leveraged_products",
        "market_rankings",
    }.issubset(inspect(schema_engine).get_table_names())

    yield PostgreSQLTestContext(database_url, schema, schema_engine)

    with schema_engine.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    schema_engine.dispose()
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
    admin_engine.dispose()


def _anchor(
    relationship_id: str = "rel_persist_test_2x",
    trading_date: date = date(2026, 9, 4),
    underlying_close: str = "1234.56789012",
    leveraged_close: str = "18.76543210",
    signed_leverage: str = "2",
    underlying_symbol: str = "PERSISTU",
    leveraged_symbol: str = "PERSISTL",
) -> DailyCloseAnchor:
    market_timestamp = datetime.combine(
        trading_date, datetime.min.time(), tzinfo=UTC
    ).replace(hour=4)
    session_closed_at = datetime.combine(
        trading_date, datetime.min.time(), tzinfo=UTC
    ).replace(hour=20)

    def value(symbol: str, close: str) -> DailyCloseAnchorValue:
        return DailyCloseAnchorValue(
            symbol=symbol,
            close=Decimal(close),
            trading_date=trading_date,
            market_timestamp=market_timestamp,
            observed_at=STAMP + timedelta(seconds=1),
            source="test",
            source_feed="sip",
            currency="USD",
            quality=DailyCloseQuality.DELAYED,
            status=DailyCloseValueStatus.AVAILABLE,
            message="accepted completed regular-session daily close",
        )

    return DailyCloseAnchor(
        id="pending",
        relationship_id=relationship_id,
        trading_date=trading_date,
        status=DailyCloseAnchorStatus.COMPLETE,
        version=0,
        underlying=value(underlying_symbol, underlying_close),
        leveraged_product=value(leveraged_symbol, leveraged_close),
        session_closed_at=session_closed_at,
        captured_at=STAMP + timedelta(seconds=2),
        provider="test",
        source_feed="sip",
        signed_leverage=Decimal(signed_leverage),
        created_at=STAMP + timedelta(seconds=2),
    )


def test_insert_latest_decimal_idempotency_and_conflict(
    postgresql_context: PostgreSQLTestContext,
) -> None:
    repository = PostgreSQLDailyCloseAnchorRepository(postgresql_context.engine)
    candidate = _anchor()

    first = repository.save(candidate)
    second = repository.save(replace(candidate, captured_at=STAMP + timedelta(minutes=1)))

    assert first.outcome == AnchorPersistenceOutcome.INSERTED
    assert second.outcome == AnchorPersistenceOutcome.EXISTING
    assert second.anchor.id == first.anchor.id
    assert first.anchor.underlying.close == Decimal("1234.56789012")
    assert first.anchor.leveraged_product.close == Decimal("18.76543210")
    assert repository.latest(candidate.relationship_id) == first.anchor
    assert repository.count_identity(
        "PERSISTU", "PERSISTL", candidate.trading_date
    ) == 1

    assert first.anchor.underlying.close is not None
    conflicting = replace(
        candidate,
        underlying=replace(
            candidate.underlying,
            close=first.anchor.underlying.close + Decimal("0.00000001"),
        ),
    )
    with pytest.raises(AnchorConflictError, match="conflicting immutable"):
        repository.save(conflicting)

    assert repository.latest(candidate.relationship_id) == first.anchor


def test_latest_selects_newest_trading_date(
    postgresql_context: PostgreSQLTestContext,
) -> None:
    repository = PostgreSQLDailyCloseAnchorRepository(postgresql_context.engine)
    relationship_id = "rel_multiple_dates_test_2x"
    older = repository.save(
        _anchor(
            relationship_id=relationship_id,
            trading_date=date(2026, 9, 3),
            underlying_symbol="MULTIU",
            leveraged_symbol="MULTIL",
        )
    ).anchor
    newer = repository.save(
        _anchor(
            relationship_id=relationship_id,
            trading_date=date(2026, 9, 4),
            underlying_symbol="MULTIU",
            leveraged_symbol="MULTIL",
        )
    ).anchor

    assert older.version == 1
    assert newer.version == 2
    assert repository.latest(relationship_id) == newer


def test_anchor_survives_engine_and_repository_recreation(
    postgresql_context: PostgreSQLTestContext,
) -> None:
    first_engine = postgresql_context.new_engine()
    stored = PostgreSQLDailyCloseAnchorRepository(first_engine).save(
        _anchor(
            relationship_id="rel_recreation_test_2x",
            underlying_symbol="RECREATEU",
            leveraged_symbol="RECREATEL",
        )
    ).anchor
    first_engine.dispose()

    second_engine = postgresql_context.new_engine()
    recreated = PostgreSQLDailyCloseAnchorRepository(second_engine).latest(
        stored.relationship_id
    )
    second_engine.dispose()

    assert recreated == stored


def test_database_trigger_rejects_mutation(
    postgresql_context: PostgreSQLTestContext,
) -> None:
    repository = PostgreSQLDailyCloseAnchorRepository(postgresql_context.engine)
    stored = repository.save(
        _anchor(
            relationship_id="rel_immutable_test_2x",
            underlying_symbol="IMMUTABLEU",
            leveraged_symbol="IMMUTABLEL",
        )
    ).anchor

    with postgresql_context.engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(DBAPIError, match="immutable"):
            connection.execute(
                text(
                    "UPDATE daily_close_anchors "
                    "SET underlying_close = underlying_close + 1 WHERE id = :id"
                ),
                {"id": stored.id},
            )
        transaction.rollback()


class FailIfDailyCloseProvider(DailyCloseMarketDataProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def provider_code(self) -> str:
        return "must-not-be-called"

    @property
    def daily_close_feed(self) -> str:
        return "must-not-be-called"

    def get_daily_close_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[DailyCloseBar]:
        self.calls += 1
        raise AssertionError("calculator read contacted the capture provider")


class FailIfMarketDataProvider(MockMarketDataProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def get_relationship(self, relationship_id: str) -> LeveragedRelationship:
        self.calls += 1
        raise AssertionError("calculator read contacted the market-data provider")


def test_calculator_read_uses_postgresql_without_market_provider_calls(
    postgresql_context: PostgreSQLTestContext,
) -> None:
    relationship_id = "rel_qqq_tqqq_3x"
    candidate = _anchor(
        relationship_id=relationship_id,
        underlying_close="480",
        leveraged_close="82.5",
        signed_leverage="3",
        underlying_symbol="QQQ",
        leveraged_symbol="TQQQ",
    )
    repository = PostgreSQLDailyCloseAnchorRepository(postgresql_context.engine)
    stored = repository.save(candidate).anchor
    capture_provider = FailIfDailyCloseProvider()
    anchor_service = DailyCloseAnchorService(
        provider=capture_provider,
        calendar=NyseTradingCalendar(),
        repository=repository,
        now=lambda: STAMP,
    )
    metadata_provider = MockMarketDataProvider()
    catalog = InMemoryLeveragedRelationshipCatalog(
        (metadata_provider.get_relationship(relationship_id),)
    )
    request_provider = FailIfMarketDataProvider()
    service = MarketDataService(request_provider, anchor_service, catalog)

    result = service.calculate(
        relationship_id=relationship_id,
        anchor_version_id=stored.id,
        input_side="underlying",
        target_price=Decimal("489.6"),
    )

    assert result.leveraged_return == Decimal("0.06")
    assert capture_provider.calls == 0
    assert request_provider.calls == 0


def test_postgresql_universe_seed_supports_search_and_multiple_products(
    postgresql_context: PostgreSQLTestContext,
) -> None:
    catalog = PostgreSQLLeveragedUniverseRepository(postgresql_context.engine)

    search = catalog.search_instruments("QQQ", 10)
    relationships = catalog.get_leveraged_relationships("ins_qqq_xnas")

    assert search[0].symbol == "QQQ"
    assert [item.leveraged_product.symbol for item in relationships] == [
        "QLD",
        "TQQQ",
        "PSQ",
        "QID",
        "SQQQ",
    ]
    assert {item.direction for item in relationships} == {"LONG", "INVERSE"}
    assert all(item.authoritative_source for item in relationships)
    assert all(item.verified_at is not None for item in relationships)

    mu_relationships = catalog.get_leveraged_relationships("ins_mu_xnas")
    assert {item.leveraged_product.symbol for item in mu_relationships} == {
        "MIC",
        "MUU",
        "MUD",
        "MULL",
        "MUG",
        "MUZ",
    }
    assert all(item.authoritative_source for item in mu_relationships)

    avgo_relationships = catalog.get_leveraged_relationships("ins_avgo_xnas")
    assert {item.leveraged_product.symbol for item in avgo_relationships} == {
        "AVGC",
        "AVGG",
        "AVGU",
        "AVGX",
        "AVL",
        "AVS",
    }

    spcx_relationships = catalog.get_leveraged_relationships("ins_spcx_xnas")
    assert len(spcx_relationships) == 13
    assert {
        item.leveraged_product.symbol: item.leverage_factor
        for item in spcx_relationships
    }["LOFD"] == Decimal("-2")
    assert {
        item.leveraged_product.symbol: item.leverage_factor
        for item in spcx_relationships
    }["DSPC"] == Decimal("-1")

    product_search = catalog.search_leveraged_products("MSTX", 10)
    assert [item.symbol for item in product_search] == ["MSTX"]

    with postgresql_context.engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM underlyings")) == 75
        assert connection.scalar(text("SELECT count(*) FROM leveraged_products")) == 264

    goog_relationships = catalog.get_leveraged_relationships("ins_goog_xnas")
    assert [item.leveraged_product.symbol for item in goog_relationships] == [
        "GOOX"
    ]
    assert catalog.get_relationship("rel_goog_goox_2x").underlying.symbol == "GOOG"


def test_postgresql_ranking_import_is_separate_and_replaceable(
    postgresql_context: PostgreSQLTestContext,
) -> None:
    repository = PostgreSQLMarketRankingRepository(
        postgresql_context.engine,
        today=lambda: date(2026, 9, 6),
    )
    empty = repository.get_dataset("2026-09", RankingType.DOLLAR_TRADING_VOLUME)
    row = MarketRanking(
        ranking_period="2026-09",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 4),
        period_status=RankingPeriodStatus.SEPTEMBER_TO_DATE,
        ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
        rank=1,
        symbol="QQQ",
        trading_metric=Decimal("999999.99"),
        calculated_at=STAMP,
        source="verified-integration-fixture",
    )

    assert empty.population_status.value == "NOT_POPULATED"
    assert repository.replace_verified_rows((row,)) == 1
    populated = repository.get_dataset(
        "2026-09", RankingType.DOLLAR_TRADING_VOLUME
    )

    assert populated.population_status.value == "PARTIAL"
    assert populated.rows == (row,)
