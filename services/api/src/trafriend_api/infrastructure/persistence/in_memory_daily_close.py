from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Dict, Tuple

from trafriend_api.application.ports.daily_close import (
    AnchorPersistenceOutcome,
    DailyCloseAnchorPersistenceResult,
    DailyCloseAnchorRepository,
)
from trafriend_api.domain.daily_close import (
    DailyCloseAnchor,
    daily_close_anchor_identity,
    daily_close_anchors_materially_equal,
)
from trafriend_api.domain.errors import AnchorConflictError, AnchorUnavailableError


class InMemoryDailyCloseAnchorRepository(DailyCloseAnchorRepository):
    """Process-local immutable anchor history for Mock and manual validation."""

    def __init__(self) -> None:
        self._anchors: Dict[str, Tuple[DailyCloseAnchor, ...]] = {}
        self._by_identity: Dict[tuple[str, str, date], DailyCloseAnchor] = {}

    def save(
        self, anchor: DailyCloseAnchor
    ) -> DailyCloseAnchorPersistenceResult:
        identity = daily_close_anchor_identity(anchor)
        existing = self._by_identity.get(identity)
        if existing is not None:
            if not daily_close_anchors_materially_equal(existing, anchor):
                raise AnchorConflictError(
                    "Daily Close Anchor already exists with conflicting immutable values"
                )
            return DailyCloseAnchorPersistenceResult(
                anchor=existing,
                outcome=AnchorPersistenceOutcome.EXISTING,
            )

        history = self._anchors.get(anchor.relationship_id, ())
        version = len(history) + 1
        stored = replace(
            anchor,
            id=(
                f"close_{anchor.relationship_id}_{anchor.trading_date.isoformat()}_"
                f"v{version}"
            ),
            version=version,
        )
        self._anchors[anchor.relationship_id] = history + (stored,)
        self._by_identity[identity] = stored
        return DailyCloseAnchorPersistenceResult(
            anchor=stored,
            outcome=AnchorPersistenceOutcome.INSERTED,
        )

    def latest(self, relationship_id: str) -> DailyCloseAnchor:
        try:
            return self._anchors[relationship_id][-1]
        except (KeyError, IndexError) as exc:
            raise AnchorUnavailableError(
                "Daily Close Anchor has not been captured for this relationship"
            ) from exc
