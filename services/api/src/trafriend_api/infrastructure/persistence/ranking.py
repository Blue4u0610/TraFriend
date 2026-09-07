from __future__ import annotations

import calendar
from datetime import date
from typing import Callable, Sequence

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import sessionmaker

from trafriend_api.application.ports.ranking import MarketRankingRepository
from trafriend_api.domain.universe import (
    MarketRanking,
    PopularDataset,
    RankingCompletenessStatus,
    RankingPeriodStatus,
    RankingPopulationStatus,
    RankingType,
)
from trafriend_api.infrastructure.persistence.models import MarketRankingRecord


def _empty_period_status(ranking_period: str, today: date) -> RankingPeriodStatus:
    if ranking_period == "2026-09" and today <= date(2026, 9, 30):
        return RankingPeriodStatus.SEPTEMBER_TO_DATE
    try:
        year_text, month_text = ranking_period.split("-", 1)
        year, month = int(year_text), int(month_text)
        period_end = date(year, month, calendar.monthrange(year, month)[1])
    except (TypeError, ValueError):
        return RankingPeriodStatus.MONTH_TO_DATE
    return (
        RankingPeriodStatus.FINAL
        if period_end < today
        else RankingPeriodStatus.MONTH_TO_DATE
    )


class InMemoryMarketRankingRepository(MarketRankingRepository):
    def __init__(
        self,
        rows: Sequence[MarketRanking] = (),
        today: Callable[[], date] = date.today,
    ) -> None:
        self._rows = tuple(rows)
        self._today = today

    def get_dataset(
        self, ranking_period: str, ranking_type: RankingType, limit: int = 100
    ) -> PopularDataset:
        rows = tuple(
            sorted(
                (
                    row
                    for row in self._rows
                    if row.ranking_period == ranking_period
                    and row.ranking_type == ranking_type
                ),
                key=lambda row: row.rank,
            )[:limit]
        )
        return _dataset(ranking_period, ranking_type, rows, self._today())

    def replace_verified_rows(self, rows: Sequence[MarketRanking]) -> int:
        validated = _validate_replacement(rows)
        if not validated:
            return 0
        first = validated[0]
        self._rows = tuple(
            row
            for row in self._rows
            if not (
                row.ranking_period == first.ranking_period
                and row.ranking_type == first.ranking_type
            )
        ) + validated
        return len(validated)


class PostgreSQLMarketRankingRepository(MarketRankingRepository):
    def __init__(
        self,
        engine: Engine,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        self._today = today

    def get_dataset(
        self, ranking_period: str, ranking_type: RankingType, limit: int = 100
    ) -> PopularDataset:
        with self._session_factory() as session:
            records = session.scalars(
                select(MarketRankingRecord)
                .where(
                    MarketRankingRecord.ranking_period == ranking_period,
                    MarketRankingRecord.ranking_type == ranking_type.value,
                )
                .order_by(MarketRankingRecord.rank)
                .limit(limit)
            ).all()
        rows = tuple(self._to_domain(record) for record in records)
        return _dataset(ranking_period, ranking_type, rows, self._today())

    def replace_verified_rows(self, rows: Sequence[MarketRanking]) -> int:
        validated = _validate_replacement(rows)
        if not validated:
            return 0
        first = validated[0]
        with self._session_factory() as session, session.begin():
            session.execute(
                delete(MarketRankingRecord).where(
                    MarketRankingRecord.ranking_period == first.ranking_period,
                    MarketRankingRecord.ranking_type == first.ranking_type.value,
                )
            )
            session.add_all(
                MarketRankingRecord(
                    ranking_period=row.ranking_period,
                    period_start=row.period_start,
                    period_end=row.period_end,
                    period_status=row.period_status.value,
                    ranking_type=row.ranking_type.value,
                    rank=row.rank,
                    symbol=row.symbol,
                    display_name=row.display_name,
                    exchange=row.exchange,
                    trading_metric=row.trading_metric,
                    calculated_at=row.calculated_at,
                    source=row.source,
                    completeness_status=row.completeness_status.value,
                    sessions_observed=row.sessions_observed,
                    sessions_expected=row.sessions_expected,
                )
                for row in validated
            )
        return len(validated)

    @staticmethod
    def _to_domain(record: MarketRankingRecord) -> MarketRanking:
        return MarketRanking(
            ranking_period=record.ranking_period,
            period_start=record.period_start,
            period_end=record.period_end,
            period_status=RankingPeriodStatus(record.period_status),
            ranking_type=RankingType(record.ranking_type),
            rank=record.rank,
            symbol=record.symbol,
            display_name=record.display_name,
            exchange=record.exchange,
            trading_metric=record.trading_metric,
            calculated_at=record.calculated_at,
            source=record.source,
            completeness_status=RankingCompletenessStatus(
                record.completeness_status
            ),
            sessions_observed=record.sessions_observed,
            sessions_expected=record.sessions_expected,
        )


def _validate_replacement(rows: Sequence[MarketRanking]) -> tuple[MarketRanking, ...]:
    validated = tuple(sorted(rows, key=lambda row: row.rank))
    if not validated:
        return ()
    first = validated[0]
    if any(
        row.ranking_period != first.ranking_period
        or row.ranking_type != first.ranking_type
        or row.period_status != first.period_status
        or row.period_start != first.period_start
        or row.period_end != first.period_end
        or row.source != first.source
        or row.calculated_at != first.calculated_at
        or row.sessions_expected != first.sessions_expected
        for row in validated
    ):
        raise ValueError("ranking import must contain one coherent dataset")
    if len({row.rank for row in validated}) != len(validated):
        raise ValueError("ranking import ranks must be unique")
    if len({row.symbol for row in validated}) != len(validated):
        raise ValueError("ranking import symbols must be unique")
    return validated


def _dataset(
    ranking_period: str,
    ranking_type: RankingType,
    rows: tuple[MarketRanking, ...],
    today: date,
) -> PopularDataset:
    period_status = (
        rows[0].period_status
        if rows
        else _empty_period_status(ranking_period, today)
    )
    population_status = (
        RankingPopulationStatus.COMPLETE
        if len(rows) == 100
        else RankingPopulationStatus.PARTIAL
        if rows
        else RankingPopulationStatus.NOT_POPULATED
    )
    return PopularDataset(
        ranking_period=ranking_period,
        period_status=period_status,
        ranking_type=ranking_type,
        population_status=population_status,
        rows=rows,
    )
