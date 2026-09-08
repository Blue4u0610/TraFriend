from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timezone
from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from trafriend_api.application.ports.daily_price import (
    DailyPricePersistenceOutcome,
    DailyPricePersistenceResult,
    DailyPriceRepository,
)
from trafriend_api.domain.daily_price import (
    DailyPriceBar,
    DailyPriceConflictError,
    daily_price_bars_equal,
)
from trafriend_api.infrastructure.persistence.daily_price_models import DailyPriceBarRecord


class InMemoryDailyPriceRepository(DailyPriceRepository):
    def __init__(self, bars: Sequence[DailyPriceBar] = ()) -> None:
        self._bars: dict[tuple[str, date], DailyPriceBar] = {}
        for bar in bars:
            self.save(bar)

    def get(self, instrument_id: str, trading_date: date) -> Optional[DailyPriceBar]:
        return self._bars.get((instrument_id, trading_date))

    def history(self, instrument_id: str, start: date, end: date) -> tuple[DailyPriceBar, ...]:
        return tuple(
            sorted(
                (
                    bar
                    for (key, day), bar in self._bars.items()
                    if key == instrument_id and start <= day <= end
                ),
                key=lambda bar: bar.trading_date,
            )
        )

    def save(self, bar: DailyPriceBar) -> DailyPricePersistenceResult:
        key = (bar.instrument_id, bar.trading_date)
        existing = self._bars.get(key)
        if existing is not None:
            if not daily_price_bars_equal(existing, bar):
                raise DailyPriceConflictError("immutable daily price bar conflicts")
            return DailyPricePersistenceResult(existing, DailyPricePersistenceOutcome.EXISTING)
        self._bars[key] = bar
        return DailyPricePersistenceResult(bar, DailyPricePersistenceOutcome.INSERTED)


class PostgreSQLDailyPriceRepository(DailyPriceRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, instrument_id: str, trading_date: date) -> Optional[DailyPriceBar]:
        with Session(self._engine) as session:
            record = self._get(session, instrument_id, trading_date)
            return self._domain(record) if record else None

    def history(self, instrument_id: str, start: date, end: date) -> tuple[DailyPriceBar, ...]:
        with Session(self._engine) as session:
            records = session.scalars(
                select(DailyPriceBarRecord)
                .where(
                    DailyPriceBarRecord.instrument_id == instrument_id,
                    DailyPriceBarRecord.trading_date >= start,
                    DailyPriceBarRecord.trading_date <= end,
                )
                .order_by(DailyPriceBarRecord.trading_date)
            )
            return tuple(self._domain(record) for record in records)

    def save(self, bar: DailyPriceBar) -> DailyPricePersistenceResult:
        with Session(self._engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"daily-price:{bar.instrument_id}:{bar.trading_date}"},
            )
            existing = self._get(session, bar.instrument_id, bar.trading_date)
            if existing is not None:
                stored = self._domain(existing)
                if not daily_price_bars_equal(stored, bar):
                    raise DailyPriceConflictError("immutable daily price bar conflicts")
                return DailyPricePersistenceResult(stored, DailyPricePersistenceOutcome.EXISTING)
            stored = replace(bar, id=str(uuid4()))
            session.add(DailyPriceBarRecord(**asdict(stored)))
            session.flush()
            return DailyPricePersistenceResult(stored, DailyPricePersistenceOutcome.INSERTED)

    @staticmethod
    def _get(
        session: Session, instrument_id: str, trading_date: date
    ) -> Optional[DailyPriceBarRecord]:
        return session.scalar(
            select(DailyPriceBarRecord).where(
                DailyPriceBarRecord.instrument_id == instrument_id,
                DailyPriceBarRecord.trading_date == trading_date,
            )
        )

    @staticmethod
    def _domain(record: DailyPriceBarRecord) -> DailyPriceBar:
        return DailyPriceBar(
            id=record.id,
            instrument_id=record.instrument_id,
            symbol=record.symbol,
            trading_date=record.trading_date,
            open=record.open,
            high=record.high,
            low=record.low,
            close=record.close,
            previous_close=record.previous_close,
            session_opened_at=record.session_opened_at.astimezone(timezone.utc),
            session_closed_at=record.session_closed_at.astimezone(timezone.utc),
            market_timestamp=record.market_timestamp.astimezone(timezone.utc),
            observed_at=record.observed_at.astimezone(timezone.utc),
            provider=record.provider,
            source_feed=record.source_feed,
            quality=record.quality,
            currency=record.currency,
            adjustment=record.adjustment,
            price_scope=record.price_scope,
        )
