from __future__ import annotations

from dataclasses import replace
from typing import Dict, Tuple

from trafriend_api.application.ports.daily_close import DailyCloseAnchorRepository
from trafriend_api.domain.daily_close import DailyCloseAnchor
from trafriend_api.domain.errors import AnchorUnavailableError


class InMemoryDailyCloseAnchorRepository(DailyCloseAnchorRepository):
    """Process-local immutable anchor history for Mock and manual validation."""

    def __init__(self) -> None:
        self._anchors: Dict[str, Tuple[DailyCloseAnchor, ...]] = {}

    def save(self, anchor: DailyCloseAnchor) -> DailyCloseAnchor:
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
        return stored

    def latest(self, relationship_id: str) -> DailyCloseAnchor:
        try:
            return self._anchors[relationship_id][-1]
        except (KeyError, IndexError) as exc:
            raise AnchorUnavailableError(
                "Daily Close Anchor has not been captured for this relationship"
            ) from exc
