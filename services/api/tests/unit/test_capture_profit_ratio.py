from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Mapping

import pytest

from trafriend_api.application.services.profit_ratio import ProfitRatioService
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent, ProfitRatioPhase
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.market_data.mock.profit_ratio import (
    build_mock_profit_ratio_repository,
)
from trafriend_api.infrastructure.persistence.in_memory_profit_ratio import (
    InMemoryProfitRatioRepository,
)
from trafriend_api.scripts import capture_profit_ratio


def test_universe_refresh_preserves_persisted_identity_and_its_observation_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_repository = build_mock_profit_ratio_repository()
    original = next(
        member for member in fixture_repository.list_constituents() if member.symbol == "NVDA"
    )
    member = replace(original, instrument_id="ins_cusip_000000001")
    repository = InMemoryProfitRatioRepository((member,))
    trading_date = date(2026, 9, 4)
    records = fixture_repository.history(original.instrument_id, trading_date, trading_date)
    for record in records:
        repository.save(replace(
            record,
            observation=replace(record.observation, instrument_id=member.instrument_id),
            price=replace(record.price, instrument_id=member.instrument_id),
        ))
    original_close = repository.latest(member.instrument_id, trading_date, ProfitRatioPhase.CLOSE)
    refresh_date = date(2026, 9, 8)
    catalog_ids = {"NVDA": "ins_nvda_new_leveraged_catalog", "AAA": "ins_aaa_xnas"}
    received_ids: list[dict[str, str]] = []

    def fetch(*, instrument_ids: Mapping[str, str]) -> tuple[NasdaqConstituent, ...]:
        received_ids.append(dict(instrument_ids))
        return (
            replace(member, instrument_id=instrument_ids["NVDA"], as_of=refresh_date),
            NasdaqConstituent(
                instrument_ids["AAA"], "AAA", "Synthetic Alpha", refresh_date,
                "QQQ_EQUITY_HOLDINGS:test",
            ),
        )

    monkeypatch.setattr(capture_profit_ratio, "fetch_qqq_constituents", fetch)
    capture_profit_ratio._refresh_universe(repository, catalog_ids)
    capture_profit_ratio._refresh_universe(repository, catalog_ids)

    assert received_ids == [
        {"NVDA": member.instrument_id, "AAA": "ins_aaa_xnas"},
        {"NVDA": member.instrument_id, "AAA": "ins_aaa_xnas"},
    ]
    assert catalog_ids["NVDA"] == "ins_nvda_new_leveraged_catalog"
    assert {item.symbol: item.instrument_id for item in repository.list_constituents()} == {
        "NVDA": member.instrument_id, "AAA": "ins_aaa_xnas",
    }
    application = ProfitRatioService(
        repository, ProfitRatioExchangeCalendar(),
        now=lambda: datetime(2026, 9, 9, 12, tzinfo=timezone.utc),
    )
    history = application.daily("NVDA", trading_date, trading_date)
    assert history.instrument_id == member.instrument_id
    assert history.status == "COMPLETE"
    assert history.rows[0].close_ratio == records[1].observation.ratio
    assert repository.latest(member.instrument_id, trading_date, ProfitRatioPhase.CLOSE) == (
        original_close
    )
