from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Dict, Sequence, Tuple

from trafriend_api.application.ports.overnight_market_data import (
    OvernightReferenceRepository,
)
from trafriend_api.domain.errors import ReferenceUnavailableError
from trafriend_api.domain.overnight import OvernightReferenceCapture, ReferenceType


class InMemoryOvernightReferenceRepository(OvernightReferenceRepository):
    """Credential-free development store with immutable, idempotent versions."""

    def __init__(self) -> None:
        self._captures: Dict[
            Tuple[date, ReferenceType, Tuple[str, ...]],
            list[OvernightReferenceCapture],
        ] = {}

    def save(self, capture: OvernightReferenceCapture) -> OvernightReferenceCapture:
        symbols = tuple(sorted(value.symbol for value in capture.values))
        key = (capture.trading_date, capture.reference_type, symbols)
        versions = self._captures.setdefault(key, [])
        if versions and self._same_observations(versions[-1], capture):
            return versions[-1]
        version = len(versions) + 1
        stored = replace(
            capture,
            id=(
                f"overnight_{capture.trading_date.isoformat()}_"
                f"{capture.reference_type.value.lower()}_v{version}"
            ),
            version=version,
        )
        versions.append(stored)
        return stored

    def latest(
        self,
        trading_date: date,
        reference_type: ReferenceType,
        symbols: Sequence[str],
    ) -> OvernightReferenceCapture:
        key = (trading_date, reference_type, tuple(sorted(symbol.upper() for symbol in symbols)))
        try:
            return self._captures[key][-1]
        except (KeyError, IndexError) as exc:
            raise ReferenceUnavailableError("overnight reference capture was not found") from exc

    @staticmethod
    def _same_observations(
        left: OvernightReferenceCapture, right: OvernightReferenceCapture
    ) -> bool:
        def signature(capture: OvernightReferenceCapture) -> tuple:
            return tuple(
                sorted(
                    (
                        value.symbol,
                        value.price,
                        value.market_timestamp,
                        value.quality,
                        value.status,
                        value.price_basis,
                    )
                    for value in capture.values
                )
            )

        return signature(left) == signature(right)

