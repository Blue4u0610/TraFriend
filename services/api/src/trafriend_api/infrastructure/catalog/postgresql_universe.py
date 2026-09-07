from __future__ import annotations

from typing import Sequence

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import sessionmaker

from trafriend_api.application.ports.market_data import LeveragedRelationshipCatalog
from trafriend_api.domain.errors import ResourceNotFoundError
from trafriend_api.domain.models import (
    Instrument,
    InstrumentCapabilities,
    LeveragedRelationship,
)
from trafriend_api.infrastructure.persistence.models import (
    LeveragedProductRecord,
    UnderlyingRecord,
)


class PostgreSQLLeveragedUniverseRepository(LeveragedRelationshipCatalog):
    """Provider-independent catalog backed by curated PostgreSQL metadata."""

    def __init__(self, engine: Engine) -> None:
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def search_instruments(self, query: str, limit: int) -> Sequence[Instrument]:
        instruments = list(self.search_underlyings(query, limit))
        instruments.extend(self.search_leveraged_products(query, limit))
        normalized = query.strip().upper()
        instruments.sort(key=lambda item: self._search_sort_key(item, normalized))
        return tuple(instruments[:limit])

    def search_underlyings(self, query: str, limit: int) -> Sequence[Instrument]:
        normalized = query.strip().upper()
        pattern = f"%{normalized}%"
        with self._session_factory() as session:
            underlyings = session.scalars(
                select(UnderlyingRecord).where(
                    UnderlyingRecord.active.is_(True),
                    or_(
                        UnderlyingRecord.symbol.ilike(pattern),
                        UnderlyingRecord.display_name.ilike(pattern),
                    ),
                )
            ).all()
        instruments = [self._underlying_to_instrument(item) for item in underlyings]
        instruments.sort(key=lambda item: self._search_sort_key(item, normalized))
        return tuple(instruments[:limit])

    def search_leveraged_products(
        self, query: str, limit: int
    ) -> Sequence[Instrument]:
        normalized = query.strip().upper()
        pattern = f"%{normalized}%"
        with self._session_factory() as session:
            products = session.scalars(
                select(LeveragedProductRecord).where(
                    LeveragedProductRecord.active.is_(True),
                    or_(
                        LeveragedProductRecord.symbol.ilike(pattern),
                        LeveragedProductRecord.display_name.ilike(pattern),
                    ),
                )
            ).all()
        instruments = [self._product_to_instrument(item) for item in products]
        instruments.sort(key=lambda item: self._search_sort_key(item, normalized))
        return tuple(instruments[:limit])

    @staticmethod
    def _search_sort_key(
        instrument: Instrument, normalized: str
    ) -> tuple[bool, bool, str]:
        return (
            instrument.symbol != normalized,
            not instrument.symbol.startswith(normalized),
            instrument.symbol,
        )

    def get_instrument(self, instrument_id: str) -> Instrument:
        with self._session_factory() as session:
            underlying = session.get(UnderlyingRecord, instrument_id)
            if underlying is not None:
                return self._underlying_to_instrument(underlying)
            product = session.get(LeveragedProductRecord, instrument_id)
            if product is not None:
                return self._product_to_instrument(product)
        raise ResourceNotFoundError("instrument was not found")

    def get_instrument_by_symbol(self, symbol: str) -> Instrument:
        normalized = symbol.strip().upper()
        with self._session_factory() as session:
            underlying = session.scalar(
                select(UnderlyingRecord).where(UnderlyingRecord.symbol == normalized)
            )
            if underlying is not None:
                return self._underlying_to_instrument(underlying)
            product = session.scalar(
                select(LeveragedProductRecord).where(
                    LeveragedProductRecord.symbol == normalized
                )
            )
            if product is not None:
                return self._product_to_instrument(product)
        raise ResourceNotFoundError("instrument was not found")

    def get_leveraged_relationships(
        self, instrument_id: str
    ) -> Sequence[LeveragedRelationship]:
        with self._session_factory() as session:
            underlying = session.get(UnderlyingRecord, instrument_id)
            if underlying is None:
                product = session.get(LeveragedProductRecord, instrument_id)
                if product is None:
                    raise ResourceNotFoundError("instrument was not found")
                underlying = session.get(UnderlyingRecord, product.underlying_id)
            if underlying is None:
                raise ResourceNotFoundError("underlying instrument was not found")
            products = session.scalars(
                select(LeveragedProductRecord).where(
                    LeveragedProductRecord.underlying_id == underlying.id,
                    LeveragedProductRecord.active.is_(True),
                )
            ).all()
            relationships = [
                self._to_relationship(underlying, product) for product in products
            ]
        relationships.sort(
            key=lambda item: (
                item.direction == "INVERSE",
                abs(item.leverage_factor),
                item.leveraged_product.symbol,
            )
        )
        return tuple(relationships)

    def list_underlyings(self) -> Sequence[Instrument]:
        with self._session_factory() as session:
            records = session.scalars(
                select(UnderlyingRecord)
                .where(UnderlyingRecord.active.is_(True))
                .order_by(UnderlyingRecord.symbol)
            ).all()
        return tuple(self._underlying_to_instrument(record) for record in records)

    def get_relationship(self, relationship_id: str) -> LeveragedRelationship:
        with self._session_factory() as session:
            product = session.scalar(
                select(LeveragedProductRecord).where(
                    LeveragedProductRecord.relationship_id == relationship_id,
                    LeveragedProductRecord.active.is_(True),
                )
            )
            if product is None:
                raise ResourceNotFoundError(
                    "leveraged product relationship was not found"
                )
            underlying = session.get(UnderlyingRecord, product.underlying_id)
            if underlying is None or not underlying.active:
                raise ResourceNotFoundError(
                    "leveraged product relationship was not found"
                )
            return self._to_relationship(underlying, product)

    @staticmethod
    def _underlying_to_instrument(record: UnderlyingRecord) -> Instrument:
        return Instrument(
            id=record.id,
            symbol=record.symbol,
            name=record.display_name,
            instrument_type=record.instrument_type,
            exchange_mic=record.exchange_mic,
            currency=record.currency,
            status="active" if record.active else "inactive",
            capabilities=InstrumentCapabilities(
                leveraged_relationships=True,
                profit_ratio=record.profit_ratio_available,
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _product_to_instrument(record: LeveragedProductRecord) -> Instrument:
        return Instrument(
            id=record.id,
            symbol=record.symbol,
            name=record.display_name,
            instrument_type="leveraged_etf",
            exchange_mic=record.exchange_mic,
            currency="USD",
            status="active" if record.active else "inactive",
            capabilities=InstrumentCapabilities(
                leveraged_relationships=True,
                profit_ratio=False,
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @classmethod
    def _to_relationship(
        cls, underlying: UnderlyingRecord, product: LeveragedProductRecord
    ) -> LeveragedRelationship:
        return LeveragedRelationship(
            id=product.relationship_id,
            underlying=cls._underlying_to_instrument(underlying),
            leveraged_product=cls._product_to_instrument(product),
            leverage_factor=product.signed_leverage,
            objective_period=product.objective_period,
            effective_from=product.effective_from,
            effective_to=product.effective_to,
            issuer=product.issuer,
            direction=product.direction,
            status="active" if product.active else "inactive",
            authoritative_source=product.authoritative_source,
            verified_at=product.verified_at,
        )
