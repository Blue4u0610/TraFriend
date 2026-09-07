from typing import Dict, Iterable, Sequence

from trafriend_api.application.ports.market_data import LeveragedRelationshipCatalog
from trafriend_api.domain.errors import ResourceNotFoundError
from trafriend_api.domain.models import Instrument, LeveragedRelationship


class InMemoryLeveragedRelationshipCatalog(LeveragedRelationshipCatalog):
    """Immutable curated metadata used without a market-data-provider call."""

    def __init__(self, relationships: Iterable[LeveragedRelationship]) -> None:
        by_id: Dict[str, LeveragedRelationship] = {}
        instruments: Dict[str, Instrument] = {}
        for relationship in relationships:
            if relationship.id in by_id:
                raise ValueError("relationship ids must be unique")
            by_id[relationship.id] = relationship
            instruments[relationship.underlying.id] = relationship.underlying
            instruments[relationship.leveraged_product.id] = (
                relationship.leveraged_product
            )
        self._relationships = by_id
        self._instruments = instruments

    def search_instruments(self, query: str, limit: int) -> Sequence[Instrument]:
        matches = list(self.search_underlyings(query, limit))
        matches.extend(self.search_leveraged_products(query, limit))
        normalized = query.strip().upper()
        matches.sort(key=lambda item: self._search_sort_key(item, normalized))
        return tuple(matches[:limit])

    def search_underlyings(self, query: str, limit: int) -> Sequence[Instrument]:
        return self._search(query, limit, leveraged_products=False)

    def search_leveraged_products(
        self, query: str, limit: int
    ) -> Sequence[Instrument]:
        return self._search(query, limit, leveraged_products=True)

    def _search(
        self, query: str, limit: int, *, leveraged_products: bool
    ) -> Sequence[Instrument]:
        normalized = query.strip().upper()
        matches = [
            instrument
            for instrument in self._instruments.values()
            if instrument.status == "active"
            and (instrument.instrument_type == "leveraged_etf")
            == leveraged_products
            and (
                normalized in instrument.symbol
                or normalized in instrument.name.upper()
            )
        ]
        matches.sort(key=lambda item: self._search_sort_key(item, normalized))
        return tuple(matches[:limit])

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
        try:
            return self._instruments[instrument_id]
        except KeyError as exc:
            raise ResourceNotFoundError("instrument was not found") from exc

    def get_instrument_by_symbol(self, symbol: str) -> Instrument:
        normalized = symbol.strip().upper()
        for instrument in self._instruments.values():
            if instrument.symbol == normalized:
                return instrument
        raise ResourceNotFoundError("instrument was not found")

    def get_leveraged_relationships(
        self, instrument_id: str
    ) -> Sequence[LeveragedRelationship]:
        instrument = self.get_instrument(instrument_id)
        if instrument.instrument_type == "leveraged_etf":
            selected = next(
                (
                    relationship
                    for relationship in self._relationships.values()
                    if relationship.leveraged_product.id == instrument.id
                ),
                None,
            )
            if selected is None:
                return ()
            underlying_id = selected.underlying.id
        else:
            underlying_id = instrument.id
        return tuple(
            sorted(
                (
                    relationship
                    for relationship in self._relationships.values()
                    if relationship.underlying.id == underlying_id
                    and relationship.status == "active"
                ),
                key=lambda item: (
                    item.direction == "INVERSE",
                    abs(item.leverage_factor),
                    item.leveraged_product.symbol,
                ),
            )
        )

    def list_underlyings(self) -> Sequence[Instrument]:
        underlying_ids = {
            relationship.underlying.id
            for relationship in self._relationships.values()
            if relationship.status == "active"
        }
        return tuple(
            sorted(
                (
                    self._instruments[instrument_id]
                    for instrument_id in underlying_ids
                    if self._instruments[instrument_id].status == "active"
                ),
                key=lambda item: item.symbol,
            )
        )

    def get_relationship(self, relationship_id: str) -> LeveragedRelationship:
        try:
            return self._relationships[relationship_id]
        except KeyError as exc:
            raise ResourceNotFoundError(
                "leveraged product relationship was not found"
            ) from exc
