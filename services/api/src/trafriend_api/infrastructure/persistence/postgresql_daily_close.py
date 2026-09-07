from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from trafriend_api.application.ports.daily_close import (
    AnchorPersistenceOutcome,
    DailyCloseAnchorPersistenceResult,
    DailyCloseAnchorRepository,
)
from trafriend_api.domain.daily_close import (
    DailyCloseAnchor,
    DailyCloseAnchorStatus,
    DailyCloseAnchorValue,
    DailyCloseQuality,
    DailyCloseValueStatus,
    daily_close_anchors_materially_equal,
)
from trafriend_api.domain.errors import AnchorConflictError, AnchorUnavailableError
from trafriend_api.infrastructure.persistence.models import DailyCloseAnchorRecord


class PostgreSQLDailyCloseAnchorRepository(DailyCloseAnchorRepository):
    """SQLAlchemy adapter for append-only, idempotent PostgreSQL anchors."""

    def __init__(
        self,
        engine: Engine,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory or sessionmaker(
            bind=engine,
            expire_on_commit=False,
        )

    def save(
        self, anchor: DailyCloseAnchor
    ) -> DailyCloseAnchorPersistenceResult:
        if anchor.status != DailyCloseAnchorStatus.COMPLETE:
            raise ValueError("PostgreSQL stores only complete Daily Close Anchors")

        with self._session_factory() as session, session.begin():
            lock_key = (
                f"{anchor.underlying.symbol}|"
                f"{anchor.leveraged_product.symbol}|{anchor.trading_date.isoformat()}"
            )
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )
            existing_record = session.scalar(
                select(DailyCloseAnchorRecord).where(
                    DailyCloseAnchorRecord.underlying_symbol
                    == anchor.underlying.symbol,
                    DailyCloseAnchorRecord.leveraged_product_symbol
                    == anchor.leveraged_product.symbol,
                    DailyCloseAnchorRecord.trading_date == anchor.trading_date,
                )
            )
            if existing_record is not None:
                existing = self._to_domain(existing_record)
                if not daily_close_anchors_materially_equal(existing, anchor):
                    raise AnchorConflictError(
                        "Daily Close Anchor already exists with conflicting immutable values"
                    )
                return DailyCloseAnchorPersistenceResult(
                    anchor=existing,
                    outcome=AnchorPersistenceOutcome.EXISTING,
                )

            latest_version = session.scalar(
                select(func.max(DailyCloseAnchorRecord.version)).where(
                    DailyCloseAnchorRecord.relationship_id == anchor.relationship_id
                )
            )
            record = self._to_record(
                anchor,
                anchor_id=str(uuid4()),
                version=int(latest_version or 0) + 1,
            )
            session.add(record)
            session.flush()
            session.refresh(record)
            stored = self._to_domain(record)
            return DailyCloseAnchorPersistenceResult(
                anchor=stored,
                outcome=AnchorPersistenceOutcome.INSERTED,
            )

    def latest(self, relationship_id: str) -> DailyCloseAnchor:
        with self._session_factory() as session:
            record = session.scalar(
                select(DailyCloseAnchorRecord)
                .where(DailyCloseAnchorRecord.relationship_id == relationship_id)
                .order_by(
                    DailyCloseAnchorRecord.trading_date.desc(),
                    DailyCloseAnchorRecord.version.desc(),
                )
                .limit(1)
            )
            if record is None:
                raise AnchorUnavailableError(
                    "Daily Close Anchor has not been captured for this relationship"
                )
            return self._to_domain(record)

    def count_identity(
        self,
        underlying_symbol: str,
        leveraged_product_symbol: str,
        trading_date: date,
    ) -> int:
        with self._session_factory() as session:
            count = session.scalar(
                select(func.count())
                .select_from(DailyCloseAnchorRecord)
                .where(
                    DailyCloseAnchorRecord.underlying_symbol
                    == underlying_symbol,
                    DailyCloseAnchorRecord.leveraged_product_symbol
                    == leveraged_product_symbol,
                    DailyCloseAnchorRecord.trading_date == trading_date,
                )
            )
            return int(count or 0)

    @staticmethod
    def _to_record(
        anchor: DailyCloseAnchor, anchor_id: str, version: int
    ) -> DailyCloseAnchorRecord:
        underlying = anchor.underlying
        leveraged = anchor.leveraged_product
        if any(
            value is None
            for value in (
                underlying.close,
                leveraged.close,
                underlying.trading_date,
                leveraged.trading_date,
                underlying.market_timestamp,
                leveraged.market_timestamp,
            )
        ):
            raise ValueError("complete Daily Close Anchor members cannot be missing")

        return DailyCloseAnchorRecord(
            id=anchor_id,
            relationship_id=anchor.relationship_id,
            underlying_symbol=underlying.symbol,
            leveraged_product_symbol=leveraged.symbol,
            signed_leverage=anchor.signed_leverage,
            trading_date=anchor.trading_date,
            underlying_trading_date=underlying.trading_date,
            leveraged_product_trading_date=leveraged.trading_date,
            status=anchor.status.value,
            version=version,
            session_closed_at=anchor.session_closed_at,
            underlying_close=underlying.close,
            leveraged_product_close=leveraged.close,
            provider=anchor.provider,
            source_feed=anchor.source_feed,
            underlying_market_timestamp=underlying.market_timestamp,
            leveraged_product_market_timestamp=leveraged.market_timestamp,
            underlying_observed_at=underlying.observed_at,
            leveraged_product_observed_at=leveraged.observed_at,
            underlying_quality=underlying.quality.value,
            leveraged_product_quality=leveraged.quality.value,
            underlying_currency=underlying.currency,
            leveraged_product_currency=leveraged.currency,
            underlying_message=underlying.message,
            leveraged_product_message=leveraged.message,
            captured_at=anchor.captured_at,
            anchor_type=anchor.anchor_type,
        )

    @staticmethod
    def _to_domain(record: DailyCloseAnchorRecord) -> DailyCloseAnchor:
        def value(
            symbol: str,
            close: Decimal,
            trading_date: date,
            market_timestamp: datetime,
            observed_at: datetime,
            currency: str,
            quality: str,
            message: str,
        ) -> DailyCloseAnchorValue:
            return DailyCloseAnchorValue(
                symbol=symbol,
                close=close,
                trading_date=trading_date,
                market_timestamp=market_timestamp,
                observed_at=observed_at,
                source=record.provider,
                source_feed=record.source_feed,
                currency=currency,
                quality=DailyCloseQuality(quality),
                status=DailyCloseValueStatus.AVAILABLE,
                message=message,
            )

        return DailyCloseAnchor(
            id=record.id,
            relationship_id=record.relationship_id,
            trading_date=record.trading_date,
            status=DailyCloseAnchorStatus(record.status),
            version=record.version,
            underlying=value(
                record.underlying_symbol,
                record.underlying_close,
                record.underlying_trading_date,
                record.underlying_market_timestamp,
                record.underlying_observed_at,
                record.underlying_currency,
                record.underlying_quality,
                record.underlying_message,
            ),
            leveraged_product=value(
                record.leveraged_product_symbol,
                record.leveraged_product_close,
                record.leveraged_product_trading_date,
                record.leveraged_product_market_timestamp,
                record.leveraged_product_observed_at,
                record.leveraged_product_currency,
                record.leveraged_product_quality,
                record.leveraged_product_message,
            ),
            session_closed_at=record.session_closed_at,
            captured_at=record.captured_at,
            provider=record.provider,
            source_feed=record.source_feed,
            signed_leverage=record.signed_leverage,
            created_at=record.created_at,
            anchor_type=record.anchor_type,
        )
