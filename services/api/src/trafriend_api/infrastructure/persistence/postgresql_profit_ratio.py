from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timezone
from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from trafriend_api.application.ports.profit_ratio import (
    ProfitRatioPersistenceOutcome,
    ProfitRatioPersistenceResult,
    ProfitRatioRepository,
)
from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioConflictError,
    ProfitRatioObservation,
    ProfitRatioPhase,
    ProfitRatioPriceObservation,
    ProfitRatioRecord,
    ProfitRatioStatus,
    price_observations_equal,
    profit_ratio_records_equal,
)
from trafriend_api.infrastructure.persistence.profit_ratio_models import (
    ProfitRatioObservationRecord,
    ProfitRatioPriceRecord,
    QqqConstituentRecord,
)


class PostgreSQLProfitRatioRepository(ProfitRatioRepository):
    """Atomic endpoint/price writes; absent model inputs never become zero ratios."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_constituents(self) -> tuple[NasdaqConstituent, ...]:
        with Session(self._engine) as session:
            latest_date = session.scalar(select(func.max(QqqConstituentRecord.as_of)))
            records = session.scalars(
                select(QqqConstituentRecord)
                .where(QqqConstituentRecord.as_of == latest_date)
                .order_by(QqqConstituentRecord.symbol)
            )
            return tuple(self._constituent(record) for record in records)

    def save_constituents(self, constituents: Sequence[NasdaqConstituent]) -> None:
        if not constituents or len({item.as_of for item in constituents}) != 1:
            raise ValueError("one nonempty dated QQQ membership snapshot is required")
        if len({item.symbol for item in constituents}) != len(constituents):
            raise ValueError("QQQ membership symbols must be unique")
        if len({item.instrument_id for item in constituents}) != len(constituents):
            raise ValueError("QQQ membership identities must be unique")
        with Session(self._engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "qqq-membership"}
            )
            existing = tuple(
                self._constituent(row)
                for row in session.scalars(
                    select(QqqConstituentRecord).where(
                        QqqConstituentRecord.as_of == constituents[0].as_of
                    )
                )
            )
            if existing:
                if set(existing) != set(constituents):
                    raise ProfitRatioConflictError("dated QQQ membership snapshot conflicts")
                return
            session.add_all(QqqConstituentRecord(**asdict(item)) for item in constituents)

    def latest(
        self, instrument_id: str, trading_date: date, phase: ProfitRatioPhase
    ) -> Optional[ProfitRatioRecord]:
        with Session(self._engine) as session:
            return self._latest(session, instrument_id, trading_date, phase)

    def history(self, instrument_id: str, start: date, end: date) -> tuple[ProfitRatioRecord, ...]:
        with Session(self._engine) as session:
            records = session.scalars(
                select(ProfitRatioObservationRecord)
                .where(
                    ProfitRatioObservationRecord.instrument_id == instrument_id,
                    ProfitRatioObservationRecord.trading_date >= start,
                    ProfitRatioObservationRecord.trading_date <= end,
                    ProfitRatioObservationRecord.methodology_key == "CHIP_TURNOVER",
                    ProfitRatioObservationRecord.methodology_version == "1",
                )
                .order_by(
                    ProfitRatioObservationRecord.trading_date,
                    ProfitRatioObservationRecord.phase,
                    ProfitRatioObservationRecord.version.desc(),
                )
            )
            latest: dict[tuple[date, str], ProfitRatioRecord] = {}
            for record in records:
                key = (record.trading_date, record.phase)
                if key not in latest:
                    latest[key] = self._domain(session, record)
            return tuple(latest.values())

    def save(self, record: ProfitRatioRecord) -> ProfitRatioPersistenceResult:
        observation, price = record.observation, record.price
        if (observation.methodology_key, observation.methodology_version) != ("CHIP_TURNOVER", "1"):
            raise ValueError("unsupported Profit Ratio methodology")
        with Session(self._engine) as session, session.begin():
            key = (f"profit-ratio:{observation.instrument_id}:"
                   f"{observation.trading_date}:{observation.phase.value}")
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
            existing = self._latest(
                session, observation.instrument_id, observation.trading_date, observation.phase
            )
            outcome = ProfitRatioPersistenceOutcome.INSERTED
            version = 1
            if existing:
                if profit_ratio_records_equal(existing, record):
                    return ProfitRatioPersistenceResult(
                        existing, ProfitRatioPersistenceOutcome.EXISTING
                    )
                if not (
                    existing.observation.status == ProfitRatioStatus.DATA_INSUFFICIENT
                    and observation.status == ProfitRatioStatus.ESTIMATED
                    and price_observations_equal(existing.price, price)
                ):
                    raise ProfitRatioConflictError("immutable Profit Ratio capture conflicts")
                version = existing.observation.version + 1
                outcome = ProfitRatioPersistenceOutcome.UPGRADED
            price_record = session.scalar(
                select(ProfitRatioPriceRecord).where(
                    ProfitRatioPriceRecord.instrument_id == price.instrument_id,
                    ProfitRatioPriceRecord.trading_date == price.trading_date,
                    ProfitRatioPriceRecord.phase == price.phase.value,
                )
            )
            if price_record is None:
                price_record = ProfitRatioPriceRecord(id=str(uuid4()), **asdict(price))
                session.add(price_record)
                session.flush()
            elif any(
                getattr(price_record, key) != value
                for key, value in asdict(price).items()
                if key != "observed_at"
            ):
                raise ProfitRatioConflictError("immutable Profit Ratio price context conflicts")
            stored_observation = replace(observation, id=str(uuid4()), version=version)
            stored = ProfitRatioObservationRecord(
                id=stored_observation.id,
                price_id=price_record.id,
                instrument_id=observation.instrument_id,
                trading_date=observation.trading_date,
                phase=observation.phase.value,
                ratio=observation.ratio,
                observed_at=observation.observed_at,
                quality=observation.quality,
                status=observation.status.value,
                reason_code=observation.reason_code,
                methodology_key=observation.methodology_key,
                methodology_version=observation.methodology_version,
                version=version,
            )
            session.add(stored)
            session.flush()
            return ProfitRatioPersistenceResult(self._domain(session, stored), outcome)

    def _latest(
        self, session: Session, instrument_id: str, trading_date: date, phase: ProfitRatioPhase
    ) -> Optional[ProfitRatioRecord]:
        record = session.scalar(
            select(ProfitRatioObservationRecord)
            .where(
                ProfitRatioObservationRecord.instrument_id == instrument_id,
                ProfitRatioObservationRecord.trading_date == trading_date,
                ProfitRatioObservationRecord.phase == phase.value,
                ProfitRatioObservationRecord.methodology_key == "CHIP_TURNOVER",
                ProfitRatioObservationRecord.methodology_version == "1",
            )
            .order_by(ProfitRatioObservationRecord.version.desc())
            .limit(1)
        )
        return self._domain(session, record) if record else None

    @staticmethod
    def _domain(session: Session, row: ProfitRatioObservationRecord) -> ProfitRatioRecord:
        price = session.get(ProfitRatioPriceRecord, row.price_id)
        if price is None:
            raise ValueError("persisted Profit Ratio price context is missing")
        return ProfitRatioRecord(
            observation=ProfitRatioObservation(
                id=row.id,
                instrument_id=row.instrument_id,
                symbol=price.symbol,
                trading_date=row.trading_date,
                phase=ProfitRatioPhase(row.phase),
                ratio=row.ratio,
                market_timestamp=price.market_timestamp.astimezone(timezone.utc),
                observed_at=row.observed_at.astimezone(timezone.utc),
                provider=price.provider,
                source_feed=price.source_feed,
                quality=row.quality,
                status=ProfitRatioStatus(row.status),
                reason_code=row.reason_code,
                methodology_key=row.methodology_key,
                methodology_version=row.methodology_version,
                version=row.version,
            ),
            price=ProfitRatioPriceObservation(
                instrument_id=price.instrument_id,
                symbol=price.symbol,
                trading_date=price.trading_date,
                phase=ProfitRatioPhase(price.phase),
                price=price.price,
                previous_close=price.previous_close,
                market_timestamp=price.market_timestamp.astimezone(timezone.utc),
                observed_at=price.observed_at.astimezone(timezone.utc),
                provider=price.provider,
                source_feed=price.source_feed,
                currency=price.currency,
            ),
        )

    @staticmethod
    def _constituent(record: QqqConstituentRecord) -> NasdaqConstituent:
        return NasdaqConstituent(
            record.instrument_id, record.symbol, record.name, record.as_of, record.source
        )
