from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Optional, Sequence

from trafriend_api.application.ports.profit_ratio import (
    ProfitRatioPersistenceOutcome,
    ProfitRatioPersistenceResult,
    ProfitRatioRepository,
)
from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioConflictError,
    ProfitRatioPhase,
    ProfitRatioRecord,
    ProfitRatioStatus,
    price_observations_equal,
    profit_ratio_records_equal,
)


class InMemoryProfitRatioRepository(ProfitRatioRepository):
    def __init__(self, constituents: Sequence[NasdaqConstituent] = ()) -> None:
        self._snapshots: dict[date, tuple[NasdaqConstituent, ...]] = {}
        self._records: dict[tuple[str, date, ProfitRatioPhase], list[ProfitRatioRecord]] = {}
        if constituents:
            self.save_constituents(constituents)

    def list_constituents(self) -> Sequence[NasdaqConstituent]:
        return self._snapshots[max(self._snapshots)] if self._snapshots else ()

    def save_constituents(self, constituents: Sequence[NasdaqConstituent]) -> None:
        if not constituents:
            raise ValueError("one nonempty dated QQQ membership snapshot is required")
        if len({item.instrument_id for item in constituents}) != len(constituents):
            raise ValueError("constituent instrument IDs must be unique")
        if len({item.symbol for item in constituents}) != len(constituents):
            raise ValueError("constituent symbols must be unique")
        if len({item.as_of for item in constituents}) > 1:
            raise ValueError("a constituent snapshot must have one effective date")
        snapshot = tuple(sorted(constituents, key=lambda item: item.symbol))
        as_of = snapshot[0].as_of
        existing = self._snapshots.get(as_of)
        if existing is not None and existing != snapshot:
            raise ProfitRatioConflictError("dated QQQ membership snapshot conflicts")
        self._snapshots[as_of] = snapshot

    def latest(
        self, instrument_id: str, trading_date: date, phase: ProfitRatioPhase
    ) -> Optional[ProfitRatioRecord]:
        versions = self._records.get((instrument_id, trading_date, phase), [])
        return versions[-1] if versions else None

    def history(self, instrument_id: str, start: date, end: date) -> Sequence[ProfitRatioRecord]:
        records = [
            versions[-1]
            for (stored_id, trading_date, _phase), versions in self._records.items()
            if stored_id == instrument_id and start <= trading_date <= end
        ]
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    item.observation.trading_date,
                    item.observation.market_timestamp,
                ),
            )
        )

    def save(self, record: ProfitRatioRecord) -> ProfitRatioPersistenceResult:
        observation = record.observation
        if (observation.methodology_key, observation.methodology_version) != ("CHIP_TURNOVER", "1"):
            raise ValueError("unsupported Profit Ratio methodology")
        key = (observation.instrument_id, observation.trading_date, observation.phase)
        versions = self._records.setdefault(key, [])
        outcome = ProfitRatioPersistenceOutcome.INSERTED
        if versions:
            existing = versions[-1]
            if profit_ratio_records_equal(existing, record):
                return ProfitRatioPersistenceResult(
                    existing, ProfitRatioPersistenceOutcome.EXISTING
                )
            if (
                existing.observation.status != ProfitRatioStatus.DATA_INSUFFICIENT
                or observation.status != ProfitRatioStatus.ESTIMATED
                or not price_observations_equal(existing.price, record.price)
                or (
                    existing.observation.methodology_key,
                    existing.observation.methodology_version,
                )
                != (observation.methodology_key, observation.methodology_version)
            ):
                raise ProfitRatioConflictError("immutable Profit Ratio observation conflicts")
            outcome = ProfitRatioPersistenceOutcome.UPGRADED
        stored = replace(record, observation=replace(observation, version=len(versions) + 1))
        versions.append(stored)
        return ProfitRatioPersistenceResult(stored, outcome)
