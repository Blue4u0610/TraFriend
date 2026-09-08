from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterator, Optional, Sequence
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from trafriend_api.application.ports.profit_ratio import (
    ProfitRatioCaptureProvider,
    ProfitRatioPersistenceOutcome,
)
from trafriend_api.application.services.profit_ratio import ProfitRatioService
from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioCaptureInput,
    ProfitRatioConflictError,
    ProfitRatioObservation,
    ProfitRatioPhase,
    ProfitRatioPriceObservation,
    ProfitRatioRecord,
    ProfitRatioSession,
    ProfitRatioStatus,
)
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)
from trafriend_api.infrastructure.persistence.profit_ratio_models import ProfitRatioPriceRecord
from trafriend_api.main import create_app
from trafriend_api.settings import Settings

UTC = timezone.utc
TRADING_DATE = date(2026, 9, 4)
NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


@dataclass(frozen=True)
class ProfitRatioPostgreSQLContext:
    database_url: str = field(repr=False)
    schema: str
    engine: Engine = field(repr=False)

    def new_engine(self) -> Engine:
        return create_engine(
            self.database_url,
            connect_args={"options": f"-csearch_path={self.schema}"},
        )


@pytest.fixture(scope="module")
def postgresql_context() -> Iterator[ProfitRatioPostgreSQLContext]:
    database_url = os.getenv("TRAFRIEND_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TRAFRIEND_TEST_DATABASE_URL is not configured")
    schema = f"test_profit_ratio_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    schema_engine = create_engine(
        database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    config = Config("alembic.ini")
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    try:
        with schema_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
            connection.rollback()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert {
            "qqq_constituent_snapshots", "profit_ratio_capture_prices", "profit_ratio_observations"
        }.issubset(inspect(schema_engine).get_table_names())
        yield ProfitRatioPostgreSQLContext(database_url, schema, schema_engine)
        with schema_engine.connect() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
        assert set(inspect(schema_engine).get_table_names()) <= {"alembic_version"}
    finally:
        schema_engine.dispose()
        # This validated UUID-named test schema is the only destructive target.
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin_engine.dispose()


def _member(symbol: str, as_of: date = TRADING_DATE) -> NasdaqConstituent:
    return NasdaqConstituent(
        f"ins_test_{symbol.lower()}", symbol, f"Synthetic {symbol} Company",
        as_of, "integration-fixture",
    )


def _record(
    symbol: str,
    ratio: Optional[str] = None,
    phase: ProfitRatioPhase = ProfitRatioPhase.CLOSE,
    price: str = "110.123456789012345678901234567890",
) -> ProfitRatioRecord:
    market_timestamp = datetime(2026, 9, 4, 20, tzinfo=UTC)
    if phase == ProfitRatioPhase.OPEN:
        market_timestamp = datetime(2026, 9, 4, 13, 30, tzinfo=UTC)
    observation_time = market_timestamp + timedelta(minutes=20)
    instrument_id = _member(symbol).instrument_id
    return ProfitRatioRecord(
        observation=ProfitRatioObservation(
            id="pending", instrument_id=instrument_id, symbol=symbol,
            trading_date=TRADING_DATE, phase=phase,
            ratio=Decimal(ratio) if ratio is not None else None,
            market_timestamp=market_timestamp, observed_at=observation_time,
            provider="mock", source_feed="mock-profit-ratio-test", quality="MOCK",
            status=ProfitRatioStatus.ESTIMATED if ratio is not None
            else ProfitRatioStatus.DATA_INSUFFICIENT,
            reason_code="" if ratio is not None else "VALIDATED_PRIOR_DISTRIBUTION_MISSING",
        ),
        price=ProfitRatioPriceObservation(
            instrument_id=instrument_id, symbol=symbol, trading_date=TRADING_DATE,
            phase=phase, price=Decimal(price), previous_close=Decimal("100"),
            market_timestamp=market_timestamp, observed_at=observation_time,
            provider="mock", source_feed="mock-profit-ratio-test",
        ),
    )


def _counts(context: ProfitRatioPostgreSQLContext, instrument_id: str) -> tuple[int, int]:
    with context.engine.connect() as connection:
        prices = connection.scalar(text(
            "SELECT count(*) FROM profit_ratio_capture_prices WHERE instrument_id = :id"
        ), {"id": instrument_id})
        ratios = connection.scalar(text(
            "SELECT count(*) FROM profit_ratio_observations WHERE instrument_id = :id"
        ), {"id": instrument_id})
    return int(prices or 0), int(ratios or 0)


def test_postgresql_membership_snapshots_are_idempotent_and_immutable(
    postgresql_context: ProfitRatioPostgreSQLContext,
) -> None:
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    members = (_member("SNAPAAA", date(2026, 9, 1)), _member("SNAPBBB", date(2026, 9, 1)))
    repository.save_constituents(members)
    repository.save_constituents(tuple(reversed(members)))
    assert repository.list_constituents() == members
    with postgresql_context.engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT count(*) FROM qqq_constituent_snapshots WHERE as_of = :as_of"
        ), {"as_of": date(2026, 9, 1)}) == 2
    with pytest.raises(ProfitRatioConflictError):
        repository.save_constituents((replace(members[0], name="Changed"), members[1]))
    newer = (_member("SNAPCCC", date(2026, 9, 2)),)
    repository.save_constituents(newer)
    assert repository.list_constituents() == newer
    with postgresql_context.engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT count(*) FROM qqq_constituent_snapshots WHERE as_of = :as_of"
        ), {"as_of": date(2026, 9, 1)}) == 2


def test_postgresql_ratio_null_upgrade_appends_version_and_preserves_decimal_precision(
    postgresql_context: ProfitRatioPostgreSQLContext,
) -> None:
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    candidate = _record("UPGRADE")
    first = repository.save(candidate)
    retry = replace(candidate,
                    observation=replace(candidate.observation, observed_at=NOW),
                    price=replace(candidate.price, observed_at=NOW))
    existing = repository.save(retry)
    assert first.outcome == ProfitRatioPersistenceOutcome.INSERTED
    assert first.record.observation.ratio is None
    assert first.record.observation.version == 1
    assert existing.outcome == ProfitRatioPersistenceOutcome.EXISTING
    assert existing.record == first.record
    assert first.record.price.price == candidate.price.price
    upgraded = repository.save(_record("UPGRADE", ratio="0.812345678901234567890123456789"))
    assert upgraded.outcome == ProfitRatioPersistenceOutcome.UPGRADED
    assert upgraded.record.observation.version == 2
    assert upgraded.record.observation.id != first.record.observation.id
    assert upgraded.record.observation.ratio == Decimal("0.812345678901234567890123456789")
    assert _counts(postgresql_context, candidate.price.instrument_id) == (1, 2)
    assert repository.save(upgraded.record).record.observation.id == upgraded.record.observation.id
    assert repository.latest(candidate.price.instrument_id, TRADING_DATE,
                             ProfitRatioPhase.CLOSE) == upgraded.record
    assert repository.history(candidate.price.instrument_id, TRADING_DATE,
                              TRADING_DATE) == (upgraded.record,)
    with postgresql_context.engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT ratio FROM profit_ratio_observations WHERE id = :id"
        ), {"id": first.record.observation.id}) is None
    recreated_engine = postgresql_context.new_engine()
    try:
        recreated = PostgreSQLProfitRatioRepository(recreated_engine).latest(
            candidate.price.instrument_id, TRADING_DATE, ProfitRatioPhase.CLOSE
        )
        assert recreated == upgraded.record
    finally:
        recreated_engine.dispose()


def test_postgresql_ratio_conflicts_do_not_change_price_or_append_observation(
    postgresql_context: ProfitRatioPostgreSQLContext,
) -> None:
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    stored = repository.save(_record("CONFLICT", ratio="0.8")).record
    with pytest.raises(ProfitRatioConflictError):
        repository.save(_record("CONFLICT", ratio="0.9"))
    with pytest.raises(ProfitRatioConflictError):
        repository.save(_record("CONFLICT", ratio="0.8", price="111"))
    assert _counts(postgresql_context, stored.price.instrument_id) == (1, 1)
    assert repository.latest(stored.price.instrument_id, TRADING_DATE,
                             ProfitRatioPhase.CLOSE) == stored


def test_postgresql_failed_observation_insert_rolls_back_new_price(
    postgresql_context: ProfitRatioPostgreSQLContext,
) -> None:
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    candidate = _record("ATOMIC")
    invalid = replace(candidate, observation=replace(candidate.observation, reason_code="X" * 101))
    with pytest.raises(DBAPIError):
        repository.save(invalid)
    assert _counts(postgresql_context, candidate.price.instrument_id) == (0, 0)
    assert repository.save(candidate).outcome == ProfitRatioPersistenceOutcome.INSERTED
    assert _counts(postgresql_context, candidate.price.instrument_id) == (1, 1)


def test_postgresql_reusing_preexisting_price_requires_immutable_equality(
    postgresql_context: ProfitRatioPostgreSQLContext,
) -> None:
    candidate = _record("ORPHAN")
    with Session(postgresql_context.engine) as session, session.begin():
        session.add(ProfitRatioPriceRecord(id=str(uuid4()), **asdict(candidate.price)))
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    conflicting = replace(candidate, price=replace(candidate.price, price=Decimal("999")))
    with pytest.raises(ProfitRatioConflictError):
        repository.save(conflicting)
    assert _counts(postgresql_context, candidate.price.instrument_id) == (1, 0)
    repository.save(candidate)
    assert _counts(postgresql_context, candidate.price.instrument_id) == (1, 1)


@pytest.mark.parametrize("verb", ["UPDATE", "DELETE"])
@pytest.mark.parametrize("table", [
    "profit_ratio_observations", "profit_ratio_capture_prices", "qqq_constituent_snapshots"
])
def test_postgresql_triggers_reject_direct_mutation(
    postgresql_context: ProfitRatioPostgreSQLContext, table: str, verb: str,
) -> None:
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    repository.save(_record("TRIGGER"))
    member = _member("TRIGGER", date(2026, 9, 3))
    repository.save_constituents((member,))
    statement = (
        f"UPDATE {table} SET instrument_id = instrument_id WHERE instrument_id = :id"
        if verb == "UPDATE" else f"DELETE FROM {table} WHERE instrument_id = :id"
    )
    with postgresql_context.engine.connect() as connection:
        transaction = connection.begin()
        try:
            with pytest.raises(DBAPIError, match="immutable"):
                connection.execute(text(statement), {"id": member.instrument_id})
        finally:
            transaction.rollback()


class RejectCaptureProvider(ProfitRatioCaptureProvider):
    def __init__(self) -> None:
        self.calls = 0

    def get_capture_inputs(
        self, symbols: Sequence[str], session: ProfitRatioSession, phase: ProfitRatioPhase,
    ) -> Sequence[ProfitRatioCaptureInput]:
        self.calls += 1
        raise AssertionError("a stored Profit Ratio read contacted the provider")


def test_postgresql_api_reads_and_application_recreation_make_zero_provider_calls(
    postgresql_context: ProfitRatioPostgreSQLContext,
) -> None:
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    member = _member("APIAA", date(2026, 9, 8))
    repository.save_constituents((member,))
    stored_open = repository.save(_record("APIAA", "0.6", ProfitRatioPhase.OPEN, "100")).record
    stored_close = repository.save(_record("APIAA", "0.7", price="110")).record
    provider = RejectCaptureProvider()
    for _ in range(2):
        recreated_engine = postgresql_context.new_engine()
        try:
            recreated_repository = PostgreSQLProfitRatioRepository(recreated_engine)
            app = create_app(Settings(database_url=None))
            app.state.profit_ratio_service = ProfitRatioService(
                recreated_repository, ProfitRatioExchangeCalendar(), provider, now=lambda: NOW
            )
            with TestClient(app) as client:
                search = client.get("/api/v1/profit-ratio/universe/search", params={"q": "APIAA"})
                assert search.status_code == 200
                assert [item["symbol"] for item in search.json()["data"]] == ["APIAA"]
                response = client.get("/api/v1/profit-ratio/symbols/APIAA/daily", params={
                    "start": "2026-09-04", "end": "2026-09-04"
                })
                assert response.status_code == 200
                payload = response.json()["data"]
                row = payload["rows"][0]
                assert payload["status"] == "COMPLETE"
                assert payload["methodology"]["id"] == "CHIP_TURNOVER"
                assert row["open_ratio"] == "0.6"
                assert row["close_ratio"] == "0.7"
                assert row["ratio_change"] == "0.1"
                assert row["price_change_return"] == "0.1"
                assert Decimal(row["open_price"]) == Decimal("100")
                assert Decimal(row["close_price"]) == Decimal("110")
                assert payload["gaps"] == []
                unknown = client.get("/api/v1/profit-ratio/symbols/UNKNOWN/daily", params={
                    "start": "2026-09-04", "end": "2026-09-04"
                })
                assert unknown.status_code == 404
            assert recreated_repository.latest(member.instrument_id, TRADING_DATE,
                                                ProfitRatioPhase.OPEN) == stored_open
            assert recreated_repository.latest(member.instrument_id, TRADING_DATE,
                                                ProfitRatioPhase.CLOSE) == stored_close
        finally:
            recreated_engine.dispose()
    assert provider.calls == 0


def test_postgresql_data_insufficient_is_null_and_missing_days_are_not_filled(
    postgresql_context: ProfitRatioPostgreSQLContext,
) -> None:
    repository = PostgreSQLProfitRatioRepository(postgresql_context.engine)
    member = _member("GAPAA", date(2026, 9, 9))
    repository.save_constituents((member,))
    repository.save(_record("GAPAA"))
    service = ProfitRatioService(repository, ProfitRatioExchangeCalendar(), now=lambda: NOW)
    history = service.daily("GAPAA", TRADING_DATE, date(2026, 9, 8))
    assert history.status == "DATA_INSUFFICIENT"
    assert [row.trading_date for row in history.rows] == [TRADING_DATE, date(2026, 9, 8)]
    assert history.rows[0].close_ratio is None
    assert history.rows[0].close_price is not None
    assert history.rows[1].close_ratio is None
    assert history.rows[1].close_price is None
    assert {gap.reason_code for gap in history.gaps} == {
        "VALIDATED_PRIOR_DISTRIBUTION_MISSING", "NOT_CAPTURED"
    }
