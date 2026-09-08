from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent
from trafriend_api.infrastructure.catalog import qqq_initialization
from trafriend_api.infrastructure.catalog.qqq_snapshot_20260904 import bootstrap_constituents
from trafriend_api.infrastructure.persistence.in_memory_profit_ratio import (
    InMemoryProfitRatioRepository,
)

MEMBER = NasdaqConstituent(
    "ins_nvda_xnas", "NVDA", "Synthetic NVIDIA", date(2026, 9, 4), "mock-qqq-holdings"
)


def test_empty_qqq_metadata_is_initialized_once_without_market_prices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryProfitRatioRepository()
    monkeypatch.setattr(qqq_initialization, "PostgreSQLProfitRatioRepository", lambda _: repository)
    snapshot = MagicMock(return_value=(MEMBER,))
    monkeypatch.setattr(qqq_initialization, "bootstrap_constituents", snapshot)
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value = [
        SimpleNamespace(symbol="NVDA", id="ins_nvda_xnas")
    ]

    assert qqq_initialization.ensure_qqq_constituents(engine) == (MEMBER,)
    assert qqq_initialization.ensure_qqq_constituents(engine) == (MEMBER,)
    snapshot.assert_called_once_with()
    engine.connect.assert_called_once()
    assert repository.history(MEMBER.instrument_id, MEMBER.as_of, MEMBER.as_of) == ()


def test_existing_metadata_does_not_depend_on_issuer_or_price_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    monkeypatch.setattr(qqq_initialization, "PostgreSQLProfitRatioRepository", lambda _: repository)
    snapshot = MagicMock(side_effect=AssertionError("existing metadata must not be replaced"))
    monkeypatch.setattr(qqq_initialization, "bootstrap_constituents", snapshot)
    engine = MagicMock()
    assert qqq_initialization.ensure_qqq_constituents(engine) == (MEMBER,)
    snapshot.assert_not_called()
    engine.connect.assert_not_called()


def test_verified_bootstrap_metadata_is_dated_complete_and_has_no_price_requirements() -> None:
    members = bootstrap_constituents()
    assert len(members) == len({member.instrument_id for member in members}) == 102
    assert len({member.symbol for member in members}) == 102
    assert {member.as_of for member in members} == {date(2026, 9, 4)}
    assert {member.source for member in members} == {"QQQ_EQUITY_HOLDINGS:Invesco"}
    assert {"NVDA", "SNDK", "AAPL"} <= {member.symbol for member in members}
    assert not {"QQQ", "SNXX", "TQQQ"} & {member.symbol for member in members}
