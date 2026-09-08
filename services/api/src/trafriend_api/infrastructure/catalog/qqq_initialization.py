"""Dated metadata bootstrap, without vendor calls or search-request side effects."""

from dataclasses import replace

from sqlalchemy import Engine, select

from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent
from trafriend_api.infrastructure.catalog.qqq_snapshot_20260904 import bootstrap_constituents
from trafriend_api.infrastructure.persistence.models import UnderlyingRecord
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)


def ensure_qqq_constituents(engine: Engine) -> tuple[NasdaqConstituent, ...]:
    repository = PostgreSQLProfitRatioRepository(engine)
    existing = repository.list_constituents()
    if existing:
        return existing
    with engine.connect() as connection:
        ids = {
            row.symbol: row.id
            for row in connection.execute(select(UnderlyingRecord.symbol, UnderlyingRecord.id))
        }
    members = tuple(
        replace(member, instrument_id=ids.get(member.symbol, member.instrument_id))
        for member in bootstrap_constituents()
    )
    repository.save_constituents(members)
    return repository.list_constituents()
